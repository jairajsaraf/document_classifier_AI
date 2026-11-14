"""
Classification Engine
Core LLM-based document classification with dual verification
"""
import base64
import json
import re
from pathlib import Path

import anthropic
import openai
from typing import Dict, List, Optional, Tuple
from loguru import logger

from backend.config import settings
from backend.services.prompt_manager import PromptManager
from backend.services.document_processor import DocumentProcessor
from backend.services.pii_detector import PIIDetector
from backend.services.content_safety import ContentSafetyChecker

SENSITIVITY_LEVELS = ("Public", "Confidential", "Highly Sensitive")
# Native PDF request shapes (docs/FEATURES.md). Citations and output_config.format cannot share a request
# (Citations docs: the API returns 400), hence three shapes.
PDF_MODES = ("pdf_citations", "pdf_two_call", "pdf_structured")


def _as_bool(v) -> bool:
    """The model may answer true/false or "yes"/"no"."""
    return v is True or str(v).strip().lower() in ("true", "yes")


def _norm(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def quote_on_page(quote, page_text) -> bool:
    """Every '...'-separated segment of the quote must appear on the page (whitespace/case-insensitive)."""
    segs = [_norm(s).strip("\"'“”‘’ ") for s in re.split(r"\.\.\.|…", quote or "")]
    segs = [s for s in segs if s]
    page = _norm(page_text)
    return bool(segs) and all(s in page for s in segs)


def _text(message) -> str:
    # Haiku 5.5 may lead with a thinking block: read text blocks by type
    return "".join(b.text for b in message.content if b.type == "text")


def _schema(with_citations: bool) -> Dict:
    """JSON schema for output_config.format. No minimum/maximum: the Structured outputs docs reject them."""
    props = {
        "sensitivity": {"type": "string", "enum": list(SENSITIVITY_LEVELS)},
        "unsafe": {"type": "boolean"},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "reasoning": {"type": "string", "description": "Short explanation of the decision"},
    }
    if with_citations:
        cite = {
            "page_number": {"type": "integer"},
            "evidence_type": {"type": "string", "enum": ["text", "image"]},
            "evidence_text": {"type": "string"},
            "relevance": {"type": "string"},
        }
        props["citations"] = {"type": "array", "items": {
            "type": "object", "properties": cite, "required": list(cite), "additionalProperties": False}}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


class DocumentClassifier:
    """Main classification engine using LLMs"""

    def __init__(self):
        self.prompt_manager = PromptManager()
        self.doc_processor = DocumentProcessor()
        self.pii_detector = PIIDetector()
        self.safety_checker = ContentSafetyChecker()

        # Initialize LLM clients
        if settings.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        else:
            self.anthropic_client = None
            logger.warning("Anthropic API key not set")

        if settings.OPENAI_API_KEY:
            openai.api_key = settings.OPENAI_API_KEY
            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.openai_client = None
            logger.warning("OpenAI API key not set")

    def classify_document(
        self,
        file_path: str,
        use_dual_verification: bool = None
    ) -> Dict:
        """
        Main entry point for document classification

        Args:
            file_path: Path to document file
            use_dual_verification: Override dual verification setting

        Returns:
            Complete classification results
        """
        logger.info(f"Starting classification for: {file_path}")

        if use_dual_verification is None:
            use_dual_verification = settings.USE_DUAL_VERIFICATION

        try:
            # Step 1: Process document (extract text, images, metadata)
            logger.info("Step 1: Processing document...")
            doc_content = self.doc_processor.process_document(file_path)

            # Step 2: Pre-processing checks
            logger.info("Step 2: Pre-processing checks...")
            if not doc_content["is_legible"]:
                logger.warning(
                    f"Document has low legibility score: {doc_content['legibility_score']}"
                )

            # Get all text
            all_text = self.doc_processor.get_all_text(doc_content)

            # Step 3: PII Detection
            logger.info("Step 3: Detecting PII...")
            pii_results = self.pii_detector.detect_pii_in_pages(doc_content["pages"])

            # Step 4: Content Safety Check
            logger.info("Step 4: Checking content safety...")
            # Regex flags are a hint to the LLM and a HITL trigger; they never replace the sensitivity label
            safety_results = self.safety_checker.check_pages_safety(doc_content["pages"])

            # Step 5: Primary Classification
            logger.info("Step 5: Running primary classification...")
            primary_result = self._classify_with_llm(
                all_text,
                doc_content,
                pii_results,
                safety_results,
                model=settings.PRIMARY_LLM_MODEL,
                file_path=file_path
            )
            # Structured outputs docs: the capitalisation of enum values is not guaranteed
            said = _norm(str(primary_result.get("sensitivity")))
            primary_result["sensitivity"] = next(
                (s for s in SENSITIVITY_LEVELS if s.casefold() == said), primary_result.get("sensitivity"))
            if primary_result.get("sensitivity") not in SENSITIVITY_LEVELS:
                raise ValueError(f"model returned no valid sensitivity: {primary_result.get('sensitivity')!r}")
            primary_result["unsafe"] = _as_bool(primary_result.get("unsafe"))

            # Step 6: Dual Verification (if enabled)
            verification_result = None
            if use_dual_verification:
                logger.info("Step 6: Running dual verification...")
                verification_result = self._verify_classification(
                    all_text,
                    doc_content,
                    primary_result
                )

                # Check agreement
                agreement_score = self._calculate_agreement(
                    primary_result,
                    verification_result
                )
                primary_result["verification"] = {
                    "verified": True,
                    "agreement_score": agreement_score,
                    "secondary_result": verification_result
                }

            # Step 7: Generate Citations
            logger.info("Step 7: Generating citations...")
            citations = self._generate_citations(
                doc_content,
                primary_result,
                pii_results,
                safety_results
            )
            primary_result["citations"] = citations

            # Step 8: Check HITL triggers
            logger.info("Step 8: Checking HITL triggers...")
            hitl_decision = self.prompt_manager.check_hitl_triggers(
                primary_result,
                pii_results,
                safety_results
            )

            # Compile final result
            final_result = {
                "status": "completed",
                "sensitivity": primary_result["sensitivity"],
                "unsafe": primary_result["unsafe"],
                "confidence": primary_result.get("confidence"),
                "reasoning": primary_result.get("reasoning"),
                "summary": primary_result.get("summary"),
                "citations": citations,
                "document_metadata": self._extract_metadata(doc_content),
                "pii_results": pii_results,
                "safety_results": safety_results,
                "hitl_decision": hitl_decision,
                "model_used": settings.PRIMARY_LLM_MODEL,
                "verification": primary_result.get("verification")
            }

            logger.info(
                f"Classification complete: {final_result['sensitivity']}, unsafe={final_result['unsafe']} "
                f"(confidence: {final_result['confidence']:.2f})"
            )

            return final_result

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "document_metadata": {}
            }

    def _classify_with_llm(
        self,
        text: str,
        doc_content: Dict,
        pii_results: Dict,
        safety_results: Dict,
        model: str = None,
        file_path: str = None
    ) -> Dict:
        """
        Perform classification using LLM

        Args:
            text: Document text
            doc_content: Full document content
            pii_results: PII detection results
            safety_results: Safety check results
            model: Model to use (defaults to PRIMARY_LLM_MODEL)
            file_path: the source file, sent as is when LLM_INPUT_MODE is a native PDF shape

        Returns:
            Classification result
        """
        if model is None:
            model = settings.PRIMARY_LLM_MODEL

        mode = settings.LLM_INPUT_MODE
        if mode in PDF_MODES and "claude" in model.lower() and str(file_path).lower().endswith(".pdf"):
            return self._classify_pdf(mode, file_path, pii_results, safety_results, model)

        # Generate prompt
        prompt = self.prompt_manager.generate_final_classification_prompt(
            text,
            pii_results,
            safety_results
        )

        # Call appropriate LLM
        if "claude" in model.lower():
            result = self._call_anthropic(prompt, model)
        elif "gpt" in model.lower():
            result = self._call_openai(prompt, model)
        else:
            raise ValueError(f"Unsupported model: {model}")

        return self._parse_classification_response(result)

    def _verify_classification(
        self,
        text: str,
        doc_content: Dict,
        primary_result: Dict
    ) -> Dict:
        """
        Verify classification with secondary LLM

        Args:
            text: Document text
            doc_content: Full document content
            primary_result: Primary classification result

        Returns:
            Verification classification result
        """
        prompt = self.prompt_manager.generate_verification_prompt(
            text,
            primary_result
        )

        model = settings.SECONDARY_LLM_MODEL

        # Call different model for verification
        if "gpt" in model.lower():
            result = self._call_openai(prompt, model)
        elif "claude" in model.lower():
            result = self._call_anthropic(prompt, model)
        else:
            raise ValueError(f"Unsupported verification model: {model}")

        return self._parse_classification_response(result)

    def _classify_pdf(self, mode: str, file_path: str, pii_results: Dict, safety_results: Dict, model: str) -> Dict:
        """Send the PDF itself (page images plus text) in one of the three PDF_MODES request shapes."""
        data = base64.standard_b64encode(Path(file_path).read_bytes()).decode("ascii")

        def ask(response_format, citations=False, schema=None, label=None):
            document = {"type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
            if citations:
                document["citations"] = {"enabled": True}
            if mode == "pdf_two_call":
                document["cache_control"] = {"type": "ephemeral"}
            prompt = self.prompt_manager.generate_final_classification_prompt(
                None, pii_results, safety_results, response_format, label)
            extra = {"output_config": {"format": {"type": "json_schema", "schema": schema}}} if schema else {}
            # PDF support docs: the document block goes before the text block
            return self._create(model, [document, {"type": "text", "text": prompt}], **extra)

        if mode == "pdf_citations":
            return self._parse_cited_lines(ask("lines", citations=True))
        structured = mode == "pdf_structured"
        result = self._parse_classification_response(
            _text(ask("schema" if structured else "label", schema=_schema(with_citations=structured))))
        if mode == "pdf_two_call" and result.get("sensitivity") in SENSITIVITY_LEVELS:
            result["citations"] = self._parse_cited_lines(ask("evidence", citations=True, label=result))["citations"]
        return result

    def _parse_cited_lines(self, message) -> Dict:
        """Parse a "field: value" reply whose text blocks carry API citations.

        Citations docs ("Get structured data with citations"): add each block's text to the current line,
        attach its citations to every line holding part of that text, and expect that neither a value nor
        a citation is guaranteed. Evidence lines without a citation are kept with no page.
        """
        lines = [["", []]]
        for block in message.content:
            if block.type != "text":
                continue
            for i, part in enumerate(block.text.split("\n")):
                if i:
                    lines.append(["", []])
                lines[-1][0] += part
                if part.strip():
                    lines[-1][1].extend(getattr(block, "citations", None) or [])
        result = {"citations": []}
        for line, cites in lines:
            name, _, value = line.partition(":")
            name, value = name.strip(" *-#").lower(), value.strip()
            if not value:
                continue
            if name in ("sensitivity", "unsafe", "confidence"):
                result.setdefault(name, value.strip(" .*`\"'"))
            elif name in ("summary", "reasoning"):
                result.setdefault(name, value)
            relevance = value if name == "evidence" else f"{name}: {value}"
            for c in cites:
                # "api": cited_text is extracted by the API, so it is a valid pointer into the PDF by construction
                result["citations"].append({
                    "page_number": getattr(c, "start_page_number", None), "evidence_type": "text",
                    "evidence_text": getattr(c, "cited_text", ""), "relevance": relevance, "source": "api"})
            if name == "evidence" and not cites:
                result["citations"].append({"page_number": None, "evidence_type": "uncited",
                                            "evidence_text": value, "relevance": value})
        try:
            result["confidence"] = float(result.get("confidence"))
        except (TypeError, ValueError):
            result["confidence"] = 0.0  # no usable score: the low-confidence HITL trigger fires
        return result

    def _create(self, model: str, content, **extra):
        """One Messages API request; `content` is the prompt string or a list of content blocks."""
        if not self.anthropic_client:
            raise ValueError("Anthropic client not initialized")

        try:
            message = self.anthropic_client.messages.create(
                model=model,
                max_tokens=settings.MAX_TOKENS,
                messages=[
                    {"role": "user", "content": content}
                ],
                **extra
            )
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise
        # Structured outputs docs: after a refusal or a max_tokens stop the reply may not match the schema
        stop = getattr(message, "stop_reason", None)
        if stop in ("refusal", "max_tokens"):
            raise ValueError(f"model stopped with {stop}")
        return message

    def _call_anthropic(self, prompt: str, model: str) -> str:
        """Call Anthropic Claude API"""
        return _text(self._create(model, prompt))

    def _call_openai(self, prompt: str, model: str) -> str:
        """Call OpenAI API"""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")

        try:
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a document classification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.TEMPERATURE,
                max_tokens=settings.MAX_TOKENS
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise

    def _parse_classification_response(self, response: str) -> Dict:
        """Parse LLM response into structured format"""
        try:
            # Try to extract JSON from response
            # Look for JSON block
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            elif "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
            else:
                json_str = response

            result = json.loads(json_str)
            return result

        except json.JSONDecodeError:
            logger.warning("Could not parse JSON response, using fallback")
            # Fallback parsing
            return {
                "sensitivity": "Unknown",
                "confidence": 0.5,
                "reasoning": response,
                "summary": "Could not parse structured response",
                "citations": []
            }

    def _generate_citations(
        self,
        doc_content: Dict,
        classification: Dict,
        pii_results: Dict,
        safety_results: Dict
    ) -> List[Dict]:
        """Generate citation evidence for classification"""
        citations = []

        # Add citations from LLM response if present; `verified` = the quote is on the cited page (F13)
        pages = {p.get("page_number"): p.get("text", "") for p in doc_content.get("pages", [])}
        for c in classification.get("citations") or []:
            if isinstance(c, dict):
                if c.get("evidence_type") != "image":
                    c["verified"] = quote_on_page(c.get("evidence_text"), pages.get(c.get("page_number"), ""))
                citations.append(c)

        # Add PII citations
        if pii_results.get("pii_detected"):
            for detection in pii_results.get("detections", []):
                citations.append({
                    "page_number": detection.get("page_number"),
                    "evidence_type": "pii",
                    "evidence_text": detection.get("context"),
                    "pii_type": detection.get("type"),
                    "relevance": f"PII detected: {detection.get('type')}",
                    "relevance_score": detection.get("confidence", 0.8)
                })

        # Add safety citations
        if not safety_results.get("is_safe"):
            for flag in safety_results.get("safety_flags", []):
                for match in flag.get("matches", []):
                    citations.append({
                        "page_number": flag.get("page_number"),
                        "evidence_type": "safety_violation",
                        "evidence_text": match.get("context"),
                        "safety_category": flag.get("category"),
                        "relevance": f"Safety flag: {flag.get('description')}",
                        "relevance_score": flag.get("confidence", 0.8)
                    })

        return citations

    def _calculate_agreement(
        self,
        primary: Dict,
        secondary: Dict
    ) -> float:
        """
        Calculate agreement score between two classifications

        Returns:
            Float between 0 and 1
        """
        # Category agreement (most important)
        category_match = 1.0 if (primary.get("sensitivity"), primary.get("unsafe")) == (
            secondary.get("sensitivity"), _as_bool(secondary.get("unsafe"))) else 0.0

        # Confidence similarity
        conf_primary = primary.get("confidence", 0.5)
        conf_secondary = secondary.get("confidence", 0.5)
        conf_diff = abs(conf_primary - conf_secondary)
        conf_similarity = 1.0 - conf_diff

        # Weighted score
        agreement = (category_match * 0.7) + (conf_similarity * 0.3)

        return agreement

    def _extract_metadata(self, doc_content: Dict) -> Dict:
        """Extract document metadata for results"""
        return {
            "page_count": doc_content.get("page_count", 0),
            "image_count": doc_content.get("image_count", 0),
            "has_text": doc_content.get("has_text", False),
            "is_legible": doc_content.get("is_legible", True),
            "legibility_score": doc_content.get("legibility_score", 1.0),
            "file_size_mb": doc_content.get("file_info", {}).get("size_mb", 0)
        }
