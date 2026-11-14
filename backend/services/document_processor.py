"""
Document Processing Service
Handles document upload, extraction, and pre-processing
"""
import os
import io
import re
from typing import Dict, List, Tuple, Optional
from PIL import Image
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from loguru import logger
import magic


class DocumentProcessor:
    """Process and extract content from multi-modal documents"""

    def __init__(self):
        self.supported_formats = ['pdf', 'png', 'jpg', 'jpeg', 'tiff']

    def validate_file(self, file_path: str, max_size_mb: int = 50) -> Dict:
        """
        Validate file type and size

        Returns:
            Dict with validation results
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "file_info": {}
        }

        # Check file exists
        if not os.path.exists(file_path):
            result["valid"] = False
            result["errors"].append("File does not exist")
            return result

        # Get file size
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size_mb > max_size_mb:
            result["valid"] = False
            result["errors"].append(f"File size ({file_size_mb:.2f}MB) exceeds maximum ({max_size_mb}MB)")

        # Detect MIME type
        try:
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(file_path)
            result["file_info"]["mime_type"] = mime_type
        except Exception as e:
            logger.warning(f"Could not detect MIME type: {e}")
            result["warnings"].append("Could not detect file type")

        # Check extension
        ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        if ext not in self.supported_formats:
            result["valid"] = False
            result["errors"].append(f"Unsupported file format: {ext}")

        result["file_info"]["size_bytes"] = file_size
        result["file_info"]["size_mb"] = file_size_mb
        result["file_info"]["extension"] = ext

        return result

    def extract_pdf_content(self, file_path: str) -> Dict:
        """
        Extract text and images from PDF

        Returns:
            Dict with extracted content
        """
        result = {
            "page_count": 0,
            "image_count": 0,
            "pages": [],
            "has_text": False,
            "is_legible": True,
            "legibility_score": 1.0
        }

        try:
            # Extract text using PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                result["page_count"] = len(pdf_reader.pages)

                for page_num, page in enumerate(pdf_reader.pages, 1):
                    text = page.extract_text()

                    page_data = {
                        "page_number": page_num,
                        "text": text,
                        "has_text": bool(text.strip()),
                        "char_count": len(text),
                        "images": []
                    }

                    if text.strip():
                        result["has_text"] = True

                    result["pages"].append(page_data)

            # Render pages with pdf2image, ONE AT A TIME: all pages of an 18-page PDF at 200 dpi held
            # together take over 500 MB and got the process OOM-killed on a 512 MB instance (docs/VERIFY.md)
            try:
                result["image_count"] = len(result["pages"])

                for idx in range(1, len(result["pages"]) + 1):
                    image = convert_from_path(file_path, dpi=200, first_page=idx, last_page=idx)[0]
                    # Check if page has text, if not, try OCR
                    page_idx = idx - 1
                    if not result["pages"][page_idx]["has_text"]:
                        ocr_text = self._perform_ocr(image)
                        result["pages"][page_idx]["text"] = ocr_text
                        result["pages"][page_idx]["ocr_used"] = True

                        if ocr_text.strip():
                            result["has_text"] = True

                    # Store image metadata
                    result["pages"][page_idx]["images"].append({
                        "image_number": idx,
                        "width": image.width,
                        "height": image.height,
                        "mode": image.mode
                    })
                    image.close()

            except Exception as e:
                logger.warning(f"Could not extract images from PDF: {e}")

            # Calculate legibility score
            result["legibility_score"] = self._calculate_legibility(result["pages"])
            result["is_legible"] = result["legibility_score"] >= 0.5

        except Exception as e:
            logger.error(f"Error extracting PDF content: {e}")
            raise

        return result

    def extract_image_content(self, file_path: str) -> Dict:
        """
        Extract text from image using OCR

        Returns:
            Dict with extracted content
        """
        result = {
            "page_count": 1,
            "image_count": 1,
            "pages": [],
            "has_text": False,
            "is_legible": True,
            "legibility_score": 1.0
        }

        try:
            image = Image.open(file_path)
            ocr_text = self._perform_ocr(image)

            page_data = {
                "page_number": 1,
                "text": ocr_text,
                "has_text": bool(ocr_text.strip()),
                "char_count": len(ocr_text),
                "ocr_used": True,
                "images": [{
                    "image_number": 1,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode
                }]
            }

            result["pages"].append(page_data)
            result["has_text"] = bool(ocr_text.strip())
            result["legibility_score"] = self._calculate_legibility(result["pages"])
            result["is_legible"] = result["legibility_score"] >= 0.5

        except Exception as e:
            logger.error(f"Error extracting image content: {e}")
            raise

        return result

    def process_document(self, file_path: str) -> Dict:
        """
        Main entry point for document processing

        Returns:
            Dict with all extracted content and metadata
        """
        logger.info(f"Processing document: {file_path}")

        # Validate file
        validation = self.validate_file(file_path)
        if not validation["valid"]:
            raise ValueError(f"Invalid file: {', '.join(validation['errors'])}")

        # Extract content based on file type
        ext = validation["file_info"]["extension"]

        if ext == 'pdf':
            content = self.extract_pdf_content(file_path)
        elif ext in ['png', 'jpg', 'jpeg', 'tiff']:
            content = self.extract_image_content(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Add file info
        content["file_info"] = validation["file_info"]

        logger.info(
            f"Document processed: {content['page_count']} pages, "
            f"{content['image_count']} images, "
            f"legibility: {content['legibility_score']:.2f}"
        )

        return content

    def _perform_ocr(self, image: Image.Image) -> str:
        """Perform OCR on an image"""
        try:
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

    def _calculate_legibility(self, pages: List[Dict]) -> float:
        """
        Calculate legibility score based on text extraction quality

        Returns:
            Float between 0 and 1
        """
        if not pages:
            return 0.0

        total_chars = sum(p.get("char_count", 0) for p in pages)
        pages_with_text = sum(1 for p in pages if p.get("has_text", False))

        # Score based on text presence and density
        text_presence_score = pages_with_text / len(pages)

        # Average characters per page (assuming decent readability at 100+ chars)
        avg_chars = total_chars / len(pages) if pages else 0
        char_density_score = min(avg_chars / 100, 1.0)

        # Combined score
        legibility_score = (text_presence_score * 0.7) + (char_density_score * 0.3)

        return legibility_score

    def get_page_content(self, content: Dict, page_number: int) -> Optional[Dict]:
        """Get content for a specific page"""
        pages = content.get("pages", [])
        for page in pages:
            if page["page_number"] == page_number:
                return page
        return None

    def get_all_text(self, content: Dict) -> str:
        """Get all text from all pages combined"""
        pages = content.get("pages", [])
        all_text = "\n\n".join(
            f"--- Page {p['page_number']} ---\n{p['text']}"
            for p in pages
            if p.get("text")
        )
        return all_text
