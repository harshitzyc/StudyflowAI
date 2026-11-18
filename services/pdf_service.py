from pypdf import PdfReader

def extract_text(pdf_path):
    """Return all text from a PDF using pypdf (pure Python, no system deps)."""
    try:
        reader = PdfReader(str(pdf_path))
        text_parts = []
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                
        full_text = "\n".join(text_parts)
        
        if not full_text.strip():
            raise ValueError("No text found. The PDF may be a scanned image without OCR.")
            
        return full_text
        
    except Exception as e:
        raise RuntimeError(f"Failed to read {pdf_path}: {e}")