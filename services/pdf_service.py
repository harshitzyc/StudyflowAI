import pdfplumber

def extract_text(pdf_path):
    """Return all text from a PDF using pdfplumber (handles messy PDFs better)."""
    text_parts = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                    
        full_text = "\n".join(text_parts)
        
        if not full_text.strip():
            raise ValueError("No text found. The PDF may be a scanned image without OCR.")
            
        return full_text
        
    except Exception as e:
        # If pdfplumber fails entirely, raise a clear error
        raise RuntimeError(f"Failed to read {pdf_path}: {e}")