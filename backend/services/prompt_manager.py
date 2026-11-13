"""
Prompt Manager Service
Manages dynamic prompt generation from the prompt library
"""
import yaml
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger


class PromptManager:
    """Manage and generate dynamic prompts for classification"""

    def __init__(self, prompt_library_path: str = None):
        if prompt_library_path is None:
            # Default to prompts directory
            prompt_library_path = Path(__file__).parent.parent / "prompts" / "prompt_library.yaml"

        self.prompt_library_path = prompt_library_path
        self.prompt_library = self._load_prompt_library()

    def _load_prompt_library(self) -> Dict:
        """Load prompt library from YAML file"""
        try:
            with open(self.prompt_library_path, 'r') as f:
                library = yaml.safe_load(f)
            logger.info(f"Loaded prompt library from {self.prompt_library_path}")
            return library
        except Exception as e:
            logger.error(f"Failed to load prompt library: {e}")
            raise

    def get_system_prompt(self) -> str:
        """Get base system prompt"""
        return self.prompt_library.get("system_prompt", "")

    def get_category_definitions(self) -> Dict:
        """Get all category definitions"""
        return self.prompt_library.get("categories", {})

    def get_category_definition(self, category: str) -> Optional[Dict]:
        """Get definition for a specific category"""
        categories = self.get_category_definitions()
        return categories.get(category)

    def generate_classification_prompt(
        self,
        document_content: str,
        stage: str = "initial_analysis"
    ) -> str:
        """
        Generate dynamic prompt for a classification stage

        Args:
            document_content: The document text to analyze
            stage: Which stage of classification (initial_analysis, pii_detection, etc.)

        Returns:
            Complete prompt string
        """
        prompts = self.prompt_library.get("classification_prompts", {})
        stage_prompt = prompts.get(stage, "")

        if not stage_prompt:
            logger.warning(f"No prompt found for stage: {stage}")
            return document_content

        # Build complete prompt
        full_prompt = f"{self.get_system_prompt()}\n\n"
        full_prompt += f"## Category Definitions\n{self._format_categories()}\n\n"
        full_prompt += f"## Task\n{stage_prompt}\n\n"
        full_prompt += f"## Document Content\n{document_content}\n\n"
        full_prompt += f"## Instructions\n"
        full_prompt += self._get_citation_instructions()

        return full_prompt

    def generate_pii_detection_prompt(self, document_content: str) -> str:
        """Generate prompt specifically for PII detection"""
        prompts = self.prompt_library.get("classification_prompts", {})
        pii_prompt = prompts.get("pii_detection", "")

        full_prompt = f"{pii_prompt}\n\n"
        full_prompt += f"## Document Content\n{document_content}\n\n"
        full_prompt += "Provide a structured JSON response with detected PII."

        return full_prompt

    def generate_safety_check_prompt(self, document_content: str) -> str:
        """Generate prompt for content safety checking"""
        prompts = self.prompt_library.get("classification_prompts", {})
        safety_prompt = prompts.get("content_safety", "")

        full_prompt = f"{safety_prompt}\n\n"
        full_prompt += f"## Document Content\n{document_content}\n\n"
        full_prompt += "Identify any unsafe content and provide detailed explanation."

        return full_prompt

    def generate_final_classification_prompt(
        self,
        document_content: str,
        pii_results: Dict,
        safety_results: Dict
    ) -> str:
        """
        Generate final classification prompt with all context

        Args:
            document_content: Document text
            pii_results: Results from PII detection
            safety_results: Results from safety check

        Returns:
            Complete prompt for final classification
        """
        prompts = self.prompt_library.get("classification_prompts", {})
        final_prompt = prompts.get("final_classification", "")

        full_prompt = f"{self.get_system_prompt()}\n\n"
        full_prompt += f"## Category Definitions\n{self._format_categories()}\n\n"

        # Add PII context
        full_prompt += f"## PII Detection Results\n"
        if pii_results.get("pii_detected"):
            full_prompt += f"- PII Detected: Yes\n"
            full_prompt += f"- Types: {', '.join(pii_results.get('pii_types', []))}\n"
            full_prompt += f"- Severity: {pii_results.get('severity', 'unknown')}\n"
        else:
            full_prompt += "- PII Detected: No\n"

        # Add safety context
        full_prompt += f"\n## Content Safety Results\n"
        if not safety_results.get("is_safe"):
            full_prompt += f"- Content is Safe: No\n"
            full_prompt += f"- Flags: {safety_results.get('total_flags', 0)}\n"
            full_prompt += f"- Severity: {safety_results.get('overall_severity', 'unknown')}\n"
            full_prompt += f"- Categories: {', '.join(safety_results.get('categories_flagged', []))}\n"
        else:
            full_prompt += "- Content is Safe: Yes\n"

        full_prompt += f"\n## Task\n{final_prompt}\n\n"
        full_prompt += f"## Document Content\n{document_content}\n\n"
        full_prompt += f"## Instructions\n"
        full_prompt += self._get_citation_instructions()
        full_prompt += "\n\nProvide your response in the following JSON format:\n"
        full_prompt += self._get_response_format()

        return full_prompt

    def generate_verification_prompt(
        self,
        document_content: str,
        primary_classification: Dict
    ) -> str:
        """
        Generate prompt for dual-LLM verification

        Args:
            document_content: Document text
            primary_classification: Results from primary classification

        Returns:
            Verification prompt
        """
        dual_verification = self.prompt_library.get("dual_verification", {})
        base_prompt = dual_verification.get("cross_check_prompt", "")

        # Format the prompt with primary results
        prompt = base_prompt.format(
            primary_category=f"{primary_classification.get('sensitivity', 'Unknown')}, "
                             f"unsafe={primary_classification.get('unsafe')}",
            primary_confidence=primary_classification.get("confidence", 0),
            primary_reasoning=primary_classification.get("reasoning", "")
        )

        full_prompt = f"{self.get_system_prompt()}\n\n"
        full_prompt += f"## Category Definitions\n{self._format_categories()}\n\n"
        full_prompt += f"## Verification Task\n{prompt}\n\n"
        full_prompt += f"## Document Content\n{document_content}\n\n"
        full_prompt += "Provide your independent classification in JSON format."

        return full_prompt

    def check_hitl_triggers(
        self,
        classification_result: Dict,
        pii_result: Dict,
        safety_result: Dict
    ) -> Dict:
        """
        Check if Human-in-the-Loop review is needed

        Returns:
            Dict with HITL decision and reasons
        """
        hitl_triggers = self.prompt_library.get("hitl_triggers", [])
        triggered = []

        confidence = classification_result.get("confidence", 1.0)
        pii_detected = pii_result.get("pii_detected", False)
        # docx: "automatically detect Unsafe content and flag for human review"
        safety_flags = not safety_result.get("is_safe", True) or classification_result.get("unsafe") is True

        # Check each trigger condition
        for trigger in hitl_triggers:
            condition = trigger.get("condition", "")
            reason = trigger.get("reason", "")

            if "confidence_score" in condition:
                threshold = float(condition.split("<")[1].strip())
                if confidence < threshold:
                    triggered.append({
                        "condition": condition,
                        "reason": reason,
                        "value": confidence
                    })

            elif "pii_detected" in condition and "public_indicators" in condition:
                if pii_detected and classification_result.get("sensitivity") == "Public":
                    triggered.append({
                        "condition": condition,
                        "reason": reason
                    })

            elif "safety_flags_present" in condition:
                if safety_flags:
                    triggered.append({
                        "condition": condition,
                        "reason": reason
                    })

        return {
            "requires_hitl": len(triggered) > 0,
            "triggers": triggered,
            "priority": "high" if safety_flags else "medium" if pii_detected else "low"
        }

    def _format_categories(self) -> str:
        """Format category definitions as text"""
        categories = self.get_category_definitions()
        formatted = []

        for cat_name, cat_info in categories.items():
            formatted.append(f"### {cat_name}")
            formatted.append(f"Description: {cat_info.get('description', '')}")
            formatted.append(f"Keywords: {', '.join(cat_info.get('keywords', []))}")
            formatted.append("")

        formatted.append("### Unsafe flag (independent of the sensitivity level)")
        formatted.append(self.prompt_library.get("unsafe_definition", ""))
        return "\n".join(formatted)

    def _get_citation_instructions(self) -> str:
        """Get citation format instructions"""
        template = self.prompt_library.get("citation_template", "")
        return template

    def _get_response_format(self) -> str:
        """Get expected JSON response format"""
        return """
{
  "sensitivity": "Public | Confidential | Highly Sensitive",
  "unsafe": false,
  "confidence": 0.95,
  "summary": "Brief summary of the document",
  "reasoning": "Detailed explanation of classification decision",
  "citations": [
    {
      "page_number": 1,
      "evidence_type": "text",
      "evidence_text": "Excerpt from document",
      "relevance": "Why this supports the classification"
    }
  ],
  "secondary_categories": []
}
"""

    def reload_library(self):
        """Reload prompt library from file"""
        self.prompt_library = self._load_prompt_library()
        logger.info("Prompt library reloaded")
