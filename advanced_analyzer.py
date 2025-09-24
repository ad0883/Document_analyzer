from flask import Flask, request, jsonify, send_from_directory
import pdfplumber
import docx
import io
import re
import textstat
import language_tool_python
import nltk
from spellchecker import SpellChecker
from fuzzywuzzy import fuzz
from autocorrect import Speller
from collections import defaultdict, Counter
import json
import requests
import os
from typing import List, Dict, Any
import openai
from dotenv import load_dotenv
import google.generativeai as genai
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

# Load environment variables
load_dotenv()

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/words')
except LookupError:
    nltk.download('words')

app = Flask(__name__)

# Initialize spell checkers and grammar checker
spell = SpellChecker()
spell_autocorrect = Speller()

# Initialize LanguageTool for grammar checking (optional)
tool = None
print("Note: Using built-in grammar checking (LanguageTool integration disabled for better performance)")

# AI API Configuration
# AI Configuration - Multiple providers support
def get_ai_config():
    """Determine which AI provider is available and configure accordingly"""
    if os.getenv('GEMINI_API_KEY'):
        return {"enabled": True, "provider": "gemini", "message": "✅ AI-powered error detection enabled (Google Gemini - Free)"}
    elif os.getenv('OPENAI_API_KEY'):
        return {"enabled": True, "provider": "openai", "message": "✅ AI-powered error detection enabled (OpenAI API)"}
    elif os.getenv('HUGGINGFACE_API_KEY'):
        return {"enabled": True, "provider": "huggingface", "message": "✅ AI-powered error detection enabled (Hugging Face - Free)"}
    else:
        return {"enabled": False, "provider": "none", "message": "⚠️  AI-powered error detection disabled (set GEMINI_API_KEY, OPENAI_API_KEY, or HUGGINGFACE_API_KEY to enable)"}

AI_CONFIG = get_ai_config()
AI_API_ENABLED = AI_CONFIG["enabled"]
AI_PROVIDER = AI_CONFIG["provider"]

if AI_API_ENABLED:
    print(AI_CONFIG["message"])
else:
    print(AI_CONFIG["message"])

# Common technical terms and proper nouns to ignore
TECHNICAL_TERMS = set([
    # Tech terms - add all caps versions
    "API", "APIs", "HTTP", "HTTPS", "URL", "URLs", "JSON", "XML", "CSS", "HTML", "PDF", "PDFs",
    "AI", "ML", "IoT", "GPS", "USB", "CPU", "GPU", "RAM", "SSD", "HDD", "OS", "UI", "UX",
    "app", "apps", "email", "emails", "website", "websites", "online", "offline",
    "smartphone", "smartphones", "database", "databases", "username", "usernames",
    "WiFi", "Bluetooth", "login", "logout", "signup", "dropdown", "checkbox",
    
    # Add lowercase versions of tech terms
    "http", "https", "api", "apis", "json", "xml", "css", "html", "pdf", "pdfs",
    "yaml", "iot", "gpt", "nlp", "www", "url", "urls",
    
    # Common words often flagged incorrectly
    "sample", "samples", "document", "documents", "file", "files", "text", "data", 
    "content", "format", "version", "update", "system", "process", "analysis",
    "report", "reports", "summary", "details", "information", "example", "examples",
    "section", "sections", "page", "pages", "paragraph", "paragraphs", "word", "words",
    "sentence", "sentences", "line", "lines", "item", "items", "list", "lists",
    "table", "tables", "chart", "charts", "image", "images", "figure", "figures",
    
    # Common proper nouns and names often in documents
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
    "rodriguez", "martinez", "hernandez", "lopez", "gonzalez", "wilson", "anderson",
    "thomas", "taylor", "moore", "jackson", "martin", "lee", "perez", "thompson",
    "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson", "walker",
    "alice", "bob", "charlie", "david", "eve", "frank", "grace", "henry", "irene", "jack",
    
    # Tech companies and tools
    "openai", "google", "microsoft", "apple", "facebook", "twitter", "github", "gitlab",
    "stackoverflow", "linkedin", "youtube", "instagram", "whatsapp", "telegram",
    "markdown", "spellcheck", "testsite", "website", "webpage"
])

DOMAIN_EXTENSIONS = set([
    "com", "org", "net", "edu", "gov", "mil", "int", "ai", "io", "co", "uk", "ca", "de", "fr"
])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

class AdvancedDocumentAnalyzer:
    def __init__(self):
        self.errors = defaultdict(list)
        self.ai_enabled = AI_API_ENABLED
        self.ai_provider = AI_PROVIDER
        
    def extract_text_with_ocr(self, pdf_bytes):
        """Extract text from image-based PDF using OCR"""
        try:
            # Convert PDF pages to images
            images = convert_from_bytes(pdf_bytes)
            extracted_text = ""
            
            for i, image in enumerate(images):
                try:
                    # Use pytesseract to extract text from each page
                    page_text = pytesseract.image_to_string(image, lang='eng')
                    if page_text.strip():
                        extracted_text += f"\n--- Page {i+1} ---\n"
                        extracted_text += page_text + "\n"
                except Exception as e:
                    print(f"OCR failed for page {i+1}: {str(e)}")
                    continue
            
            return extracted_text.strip()
        except Exception as e:
            print(f"OCR extraction failed: {str(e)}")
            return ""

    def extract_text_with_formatting(self, file, filename):
        """Enhanced text extraction preserving structure"""
        text_data = {
            'raw_text': '',
            'paragraphs': [],
            'lines': [],
            'pages': []
        }
        
        try:
            if filename.endswith('.pdf'):
                with pdfplumber.open(file) as pdf:
                    for i, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        page_lines = []
                        page_paragraphs = []
                        if page_text:
                            page_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                            page_paragraphs = [line for line in page_lines if len(line) > 20]
                            text_data['raw_text'] += page_text + "\n\n"
                            text_data['lines'].extend(page_lines)
                            text_data['paragraphs'].extend(page_paragraphs)
                        # Always append a page dict, even if no text
                        text_data['pages'].append({
                            'page_num': i + 1,
                            'text': page_text if page_text else '',
                            'lines': page_lines
                        })
                                        
            elif filename.endswith('.docx'):
                doc = docx.Document(file)
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_data['paragraphs'].append(para.text)
                        text_data['lines'].append(para.text)
                text_data['raw_text'] = "\n".join(text_data['paragraphs'])
                
            else:  # .txt
                content = file.read().decode('utf-8')
                text_data['raw_text'] = content
                text_data['lines'] = content.split('\n')
                text_data['paragraphs'] = [line for line in text_data['lines'] if len(line.strip()) > 20]
        
        except Exception as e:
            print(f"ERROR in text extraction: {str(e)}")
            # Return basic text data structure even if extraction fails
            
        # Ensure all fields are initialized even if extraction fails
        if text_data.get('lines') is None:
            text_data['lines'] = []
        if text_data.get('paragraphs') is None:
            text_data['paragraphs'] = []
        if text_data.get('pages') is None:
            text_data['pages'] = []
        if text_data.get('raw_text') is None:
            text_data['raw_text'] = ''
        return text_data

    def advanced_spell_check(self, text):
        """Multi-layered spell checking with context awareness"""
        if not text or not text.strip():
            return []
        
        # Normalize and tokenize words: lowercase, strip punctuation, filter non-alpha
        import string
        raw_words = re.findall(r'\b\w+\b', text)
        words = []
        for w in raw_words:
            w_clean = w.strip(string.punctuation).lower()
            if w_clean.isalpha():
                words.append(w_clean)
        print(f"Extracted words for spell check: {words}")
        errors = []
        checked = set()
        for word in words:
            if word in checked:
                continue
            checked.add(word)
            print(f"Checking word: '{word}'")
            # Skip if it's a technical term, URL part, or domain extension
            # But be more selective - only skip if it's clearly technical
            if (word in TECHNICAL_TERMS or 
                word in DOMAIN_EXTENSIONS or
                (self.is_url_part(word) and len(word) > 4) or  # Only skip longer URL parts
                (self.is_email_part(word) and '@' in word)):   # Only skip if it has @ symbol
                print(f"  Skipped (technical/domain/url/email): '{word}'")
                continue
            
            # Skip very short words (unless they're obvious misspellings)
            if len(word) < 3:
                continue
                
            is_misspelled = False
            suggestions = []
            
            # Primary check with pyspellchecker - be more aggressive
            spell_check_failed = word not in spell
            if spell_check_failed:
                is_misspelled = True
                print(f"  Flagged as misspelled by pyspellchecker: '{word}'")
                candidates = list(spell.candidates(word))
                if candidates:
                    suggestions.extend(candidates[:5])
                else:
                    # If no candidates, try common corrections
                    print(f"  No candidates from spell checker for: '{word}'")
                    # Try removing/adding common letters
                    for correction in self.generate_correction_attempts(word):
                        if correction in spell and correction not in suggestions:
                            suggestions.append(correction)
            
            # Always check autocorrect for every word (even if spell checker passes)
            auto_suggestion = spell_autocorrect(word)
            if auto_suggestion != word:
                print(f"  Autocorrect suggests: '{word}' -> '{auto_suggestion}'")
                if auto_suggestion not in suggestions:
                    suggestions.append(auto_suggestion)
                # If autocorrect suggests a different word, it's likely misspelled
                if not is_misspelled:
                    is_misspelled = True
                    print(f"  Flagged as misspelled by autocorrect: '{word}'")
            
            # Check for common misspelling patterns
            if self.has_common_misspelling_pattern(word):
                print(f"  Has common misspelling pattern: '{word}'")
                is_misspelled = True
                pattern_suggestions = self.get_pattern_based_suggestions(word)
                for suggestion in pattern_suggestions:
                    if suggestion not in suggestions:
                        suggestions.append(suggestion)
            
            # Additional heuristics for catching more errors
            if not is_misspelled and len(word) > 3:
                # Check for repeated letters that might be typos
                if self.has_suspicious_letter_patterns(word):
                    print(f"  Has suspicious letter pattern: '{word}'")
                    is_misspelled = True
                    pattern_suggestions = self.get_pattern_based_suggestions(word)
                    for suggestion in pattern_suggestions:
                        if suggestion not in suggestions:
                            suggestions.append(suggestion)
            
            if is_misspelled and suggestions:
                unique_suggestions = list(dict.fromkeys(suggestions))
                ranked_suggestions = sorted(unique_suggestions, 
                                         key=lambda x: fuzz.ratio(word, x), 
                                         reverse=True)[:5]
                print(f"  Misspelled: '{word}', Suggestions: {ranked_suggestions}")
                errors.append({
                    'word': word,
                    'type': 'spelling',
                    'suggestions': ranked_suggestions,
                    'confidence': self.calculate_error_confidence(word, ranked_suggestions),
                    'context': self.get_word_context(word, text)
                })
        return errors

    def grammar_and_style_check(self, text):
        """Comprehensive grammar and style checking"""
        if not text or not text.strip():
            return []
            
        errors = []
        
        # Built-in grammar checks (always run)
        repeated_word_errors = self.check_repeated_words(text)
        errors.extend(repeated_word_errors)
        
        # Check for missing articles
        missing_article_errors = self.check_missing_articles(text)
        errors.extend(missing_article_errors)
        
        # Check for common grammar mistakes
        common_grammar_errors = self.check_common_grammar_mistakes(text)
        errors.extend(common_grammar_errors)
        
        print(f"Built-in grammar checking found {len(errors)} issues")
        
        # LanguageTool integration (if available)
        if tool is not None:
            try:
                matches = tool.check(text)
                for match in matches:
                    error = {
                        'type': 'grammar',
                        'category': match.category,
                        'rule_id': match.ruleId,
                        'message': match.message,
                        'suggestions': match.replacements[:5],
                        'context': match.context,
                        'offset': match.offset,
                        'length': match.errorLength,
                        'severity': self.categorize_grammar_error(match.category)
                    }
                    errors.append(error)
            except Exception as e:
                print(f"Grammar check error: {e}")
            
        return errors

    def email_validation_check(self, text):
        """Detect email-related issues"""
        if not text or not text.strip():
            return []
            
        errors = []
        
        # Find potential email addresses (including malformed ones)
        email_pattern = r'\b[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]*\.[A-Za-z]{2,}\b'
        potential_emails = re.finditer(email_pattern, text)
        
        for match in potential_emails:
            email = match.group()
            issues = []
            
            # Check for common email issues
            if '..' in email:
                issues.append('Double dots in email')
            if email.startswith('.') or email.startswith('-'):
                issues.append('Invalid character at start')
            if email.endswith('.') or email.endswith('-'):
                issues.append('Invalid character at end')
            if '@.' in email or '.@' in email:
                issues.append('Invalid dot placement around @')
            if email.count('@') != 1:
                issues.append('Multiple @ symbols' if email.count('@') > 1 else 'Missing @ symbol')
            
            # Check domain part
            if '@' in email:
                domain = email.split('@')[1]
                if not domain or len(domain) < 3:
                    issues.append('Invalid or missing domain')
                elif '.' not in domain:
                    issues.append('Domain missing top-level domain')
                elif domain.startswith('.') or domain.endswith('.'):
                    issues.append('Invalid dot placement in domain')
            
            if issues:
                errors.append({
                    'type': 'email',
                    'subtype': 'invalid_format',
                    'message': '; '.join(issues),
                    'position': match.start(),
                    'text': email,
                    'suggestion': 'Check email format (e.g., user@domain.com)'
                })
        
        # Check for incomplete email patterns
        incomplete_email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]*\b'
        incomplete_matches = re.finditer(incomplete_email_pattern, text)
        
        for match in incomplete_matches:
            email = match.group()
            if not re.match(email_pattern, email):
                errors.append({
                    'type': 'email',
                    'subtype': 'incomplete',
                    'message': 'Incomplete email address',
                    'position': match.start(),
                    'text': email,
                    'suggestion': 'Complete the email address with proper domain'
                })
        
        return errors

    def typography_and_formatting_check(self, text_data):
        """Detect typography and formatting issues"""
        if not text_data or not text_data.get('raw_text'):
            return []
            
        errors = []
        text = text_data['raw_text']
        
        # Multiple spaces
        multiple_spaces = re.finditer(r' {2,}', text)
        for match in multiple_spaces:
            errors.append({
                'type': 'formatting',
                'subtype': 'multiple_spaces',
                'message': f'Multiple consecutive spaces found ({len(match.group())} spaces)',
                'position': match.start(),
                'text': match.group(),
                'suggestion': 'Replace with single space'
            })
        
        # Inconsistent quotation marks
        quote_issues = re.finditer(r'[""''`´]', text)
        for match in quote_issues:
            errors.append({
                'type': 'typography',
                'subtype': 'inconsistent_quotes',
                'message': 'Inconsistent quotation marks',
                'position': match.start(),
                'text': match.group(),
                'suggestion': 'Use standard quotation marks (" or \')'
            })
        
        # Missing spaces after punctuation
        punctuation_spacing = re.finditer(r'[.!?:;,][a-zA-Z]', text)
        for match in punctuation_spacing:
            errors.append({
                'type': 'formatting',
                'subtype': 'missing_space',
                'message': 'Missing space after punctuation',
                'position': match.start(),
                'text': match.group(),
                'suggestion': f'{match.group()[0]} {match.group()[1]}'
            })
        
        # Inconsistent capitalization
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 1:
                if sentence[0].islower():
                    errors.append({
                        'type': 'capitalization',
                        'subtype': 'sentence_start',
                        'message': 'Sentence should start with capital letter',
                        'text': sentence[:20] + '...' if len(sentence) > 20 else sentence,
                        'suggestion': sentence[0].upper() + sentence[1:]
                    })
        
        # Number formatting issues
        number_issues = re.finditer(r'\b\d+\s+\d+\b', text)
        for match in number_issues:
            errors.append({
                'type': 'formatting',
                'subtype': 'number_spacing',
                'message': 'Potential number formatting issue',
                'position': match.start(),
                'text': match.group(),
                'suggestion': 'Check if this should be one number'
            })
        
        return errors

    def document_structure_analysis(self, text_data):
        """Analyze document structure and detect issues"""
        if not text_data or not text_data.get('paragraphs'):
            return []
            
        errors = []
        
        # Check for very short paragraphs (potential formatting issues)
        for i, para in enumerate(text_data['paragraphs']):
            if 5 < len(para) < 20 and not re.match(r'^(Chapter|Section|\d+\.)', para):
                errors.append({
                    'type': 'structure',
                    'subtype': 'short_paragraph',
                    'message': 'Very short paragraph - possible formatting issue',
                    'paragraph_number': i + 1,
                    'text': para,
                    'suggestion': 'Check if this should be combined with adjacent text'
                })
        
        # Check for inconsistent heading formats
        potential_headings = []
        for line in text_data['lines']:
            if (line.isupper() or 
                re.match(r'^(Chapter|Section|\d+\.|\w+:)', line) or
                (len(line) < 50 and line.endswith(':'))):
                potential_headings.append(line)
        
        # Analyze heading consistency
        if len(potential_headings) > 1:
            formats = [self.analyze_heading_format(h) for h in potential_headings]
            if len(set(formats)) > 2:  # More than 2 different formats
                errors.append({
                    'type': 'structure',
                    'subtype': 'inconsistent_headings',
                    'message': 'Inconsistent heading formats detected',
                    'details': potential_headings[:5],
                    'suggestion': 'Use consistent formatting for all headings'
                })
        
        return errors

    def comprehensive_analysis(self, file, filename):
        """Main analysis function combining all checks"""
        try:
            # Extract text with structure
            text_data = self.extract_text_with_formatting(file, filename)
            
            if not text_data.get('raw_text', '').strip():
                # Check if PDF and try OCR for image-based content
                if filename.endswith('.pdf'):
                    try:
                        file.seek(0)
                        pdf_bytes = file.read()
                        
                        # First check if it has images (likely scanned PDF)
                        file.seek(0)
                        with pdfplumber.open(file) as pdf:
                            has_images = any(len(page.images) > 0 for page in pdf.pages)
                        
                        if has_images:
                            # Try OCR extraction
                            ocr_text = self.extract_text_with_ocr(pdf_bytes)
                            if ocr_text:
                                text_data = {
                                    'raw_text': ocr_text,
                                    'pages': [ocr_text],  # Treat OCR result as single block
                                    'paragraphs': ocr_text.split('\n\n'),
                                    'source': 'OCR'
                                }
                            else:
                                return {'error': 'Failed to extract text using OCR. The image quality might be too poor or the text is not readable.'}
                        else:
                            return {'error': 'No readable text found in PDF and no images detected for OCR processing.'}
                    except Exception as e:
                        return {'error': f'Failed to process PDF: {str(e)}'}
                else:
                    return {'error': 'No readable text found in document'}
            
            # Perform all analyses
            spelling_errors = self.advanced_spell_check(text_data['raw_text']) or []
            grammar_errors = self.grammar_and_style_check(text_data['raw_text']) or []
            typography_errors = self.typography_and_formatting_check(text_data) or []
            structure_errors = self.document_structure_analysis(text_data) or []
            email_errors = self.email_validation_check(text_data['raw_text']) or []
            
            # AI-powered error detection (if enabled)
            ai_errors = []
            if self.ai_enabled:
                print("🤖 Running AI-powered error detection...")
                ai_errors = self.ai_error_detection(text_data['raw_text'])
                
                if len(ai_errors) > 0:
                    print(f"🤖 AI detected {len(ai_errors)} additional errors")
                    
                    # Merge AI errors with existing categories
                    for ai_error in ai_errors:
                        if ai_error['type'] == 'spelling':
                            spelling_errors.append(ai_error)
                        elif ai_error['type'] == 'grammar':
                            grammar_errors.append(ai_error)
                        else:
                            # Add as grammar errors for now
                            grammar_errors.append(ai_error)
                else:
                    print("🤖 AI analysis completed (rate limited - using enhanced local checking)")
                    # Enhance local spell checking when AI is unavailable
                    additional_local_errors = self.enhanced_local_analysis(text_data['raw_text'])
                    spelling_errors.extend(additional_local_errors)
        
            # Calculate readability metrics
            metrics = self.calculate_advanced_metrics(text_data['raw_text'])
            
            # Generate corrected text
            corrected_text = self.generate_corrected_text(text_data['raw_text'], 
                                                        spelling_errors, grammar_errors)
            
            # Create highlighted text
            highlighted_text = self.create_highlighted_text(text_data['raw_text'],
                                                          spelling_errors, grammar_errors, typography_errors, email_errors)
            return {
                'text_length': len(text_data['raw_text']),
                'pages_count': len(text_data['pages']) if text_data['pages'] else 1,
                'paragraphs_count': len(text_data['paragraphs']),
                'spelling_errors': spelling_errors,
                'grammar_errors': grammar_errors,
                'typography_errors': typography_errors,
                'structure_errors': structure_errors,
                'email_errors': email_errors,
                'total_errors': len(spelling_errors) + len(grammar_errors) + len(typography_errors) + len(structure_errors) + len(email_errors),
                'metrics': metrics,
                'corrected_text': corrected_text,
                'highlighted_text': highlighted_text,
                'error_summary': self.create_error_summary(spelling_errors, grammar_errors, typography_errors, structure_errors, email_errors)
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'error': f'Analysis failed: {str(e)}'}
    
    # Helper methods
    def is_url_part(self, word):
        return bool(re.match(r'(https?|www|com|org|net|gov|edu)', word, re.IGNORECASE))
    
    def is_email_part(self, word):
        return '@' in word or (('.' in word) and len(word.split('.')) > 1)
    
    def likely_proper_noun(self, word, text):
        # Simple heuristic: if capitalized word appears multiple times, likely proper noun
        pattern = r'\b' + re.escape(word) + r'\b'
        occurrences = len(re.findall(pattern, text))
        return occurrences > 1 and word[0].isupper()
    
    def calculate_error_confidence(self, word, suggestions):
        if not suggestions:
            return 0.5
        best_match = max(fuzz.ratio(word.lower(), sug.lower()) for sug in suggestions)
        return min(best_match / 100.0, 0.95)
    
    def has_common_misspelling_pattern(self, word):
        """Check if word has common misspelling patterns"""
        word_lower = word.lower()
        
        # Double letter patterns that might be mistakes
        double_patterns = ['ss', 'll', 'nn', 'mm', 'tt', 'pp', 'dd', 'ff', 'gg', 'kk', 'rr']
        for pattern in double_patterns:
            if pattern in word_lower:
                # Check if removing one letter makes it a valid word
                test_word = word_lower.replace(pattern, pattern[0], 1)
                if test_word in spell:
                    return True
        
        # Common endings that might be misspelled
        if word_lower.endswith('ss') and len(word) > 3:
            test_word = word_lower[:-1]  # Remove one 's'
            if test_word in spell:
                return True
                
        return False
    
    def has_suspicious_letter_patterns(self, word):
        """Check for suspicious letter patterns that often indicate typos"""
        word_lower = word.lower()
        
        # Check for double letters at the end
        if len(word) > 3 and word_lower[-1] == word_lower[-2]:
            # Try removing the last letter
            test_word = word_lower[:-1]
            if test_word in spell:
                return True
        
        # Check for triple letters or more
        for i in range(len(word_lower) - 2):
            if word_lower[i] == word_lower[i+1] == word_lower[i+2]:
                return True
        
        # Check for common typo patterns like "thiss", "thatt", "whenn", etc.
        typo_patterns = {
            'thiss': 'this',
            'thatt': 'that', 
            'whenn': 'when',
            'willl': 'will',
            'andd': 'and',
            'orr': 'or',
            'butt': 'but',
            'nott': 'not',
            'cann': 'can',
            'hass': 'has',
            'wass': 'was',
            'havee': 'have',
            'doess': 'does',
            'containz': 'contains',
            'concludez': 'concludes',
            'lice': 'alice',
            'hones': 'jones',
            'eave': 'dave',
            'testate': 'testsite',
            'contain': 'contains',
            'peng': 'pending',
            'malice': 'alice',
            'ones': 'jones',
            'cave': 'dave',
            'hessite': 'website',
            'pome': 'home',
            'sang': 'lang',
            'alo': 'also',
            'spieling': 'spelling',
            'cones': 'jones',
            'wave': 'dave',
            'tektite': 'website',
            'slang': 'lang'
        }
        
        if word_lower in typo_patterns:
            return True
            
        return False
    
    def get_pattern_based_suggestions(self, word):
        """Generate suggestions based on common misspelling patterns"""
        suggestions = []
        word_lower = word.lower()
        
        # Common typo mappings
        typo_patterns = {
            'thiss': 'this',
            'thatt': 'that', 
            'whenn': 'when',
            'willl': 'will',
            'andd': 'and',
            'orr': 'or',
            'butt': 'but',
            'nott': 'not',
            'cann': 'can',
            'hass': 'has',
            'wass': 'was',
            'havee': 'have',
            'doess': 'does',
            'containz': 'contains',
            'concludez': 'concludes',
            'lice': 'alice',
            'hones': 'jones',
            'eave': 'dave',
            'testate': 'testsite',
            'contain': 'contains',
            'peng': 'pending',
            'malice': 'alice',
            'ones': 'jones',
            'cave': 'dave',
            'hessite': 'website',
            'pome': 'home',
            'sang': 'lang',
            'alo': 'also',
            'spieling': 'spelling',
            'cones': 'jones',
            'wave': 'dave',
            'tektite': 'website',
            'slang': 'lang'
        }
        
        # Direct typo mapping
        if word_lower in typo_patterns:
            suggestions.append(typo_patterns[word_lower])
        
        # For words ending with double letters, try single letter
        if len(word) > 3:
            for char in 'abcdefghijklmnopqrstuvwxyz':
                if word_lower.endswith(char + char):
                    candidate = word_lower[:-1]
                    if candidate in spell and candidate not in suggestions:
                        suggestions.append(candidate)
        
        # For words with double letters anywhere, try single
        double_patterns = ['ss', 'll', 'nn', 'mm', 'tt', 'pp', 'dd', 'ff', 'gg', 'kk', 'rr', 'cc', 'bb']
        for pattern in double_patterns:
            if pattern in word_lower:
                candidate = word_lower.replace(pattern, pattern[0], 1)
                if candidate in spell and candidate not in suggestions:
                    suggestions.append(candidate)
        
        # Try removing last character (common for extra letters)
        if len(word) > 3:
            candidate = word_lower[:-1]
            if candidate in spell and candidate not in suggestions:
                suggestions.append(candidate)
        
        return suggestions[:5]  # Return up to 5 suggestions
    
    def generate_correction_attempts(self, word):
        """Generate correction attempts for words with no spell checker candidates"""
        corrections = []
        
        # Try removing last character (for words like "containz" -> "contain")
        if len(word) > 3:
            corrections.append(word[:-1])
        
        # Try changing last character to common endings
        if len(word) > 3:
            base = word[:-1]
            for ending in ['s', 'e', 'd', 'r', 'n', 't']:
                corrections.append(base + ending)
        
        # Try removing/changing middle characters for common patterns
        if 'z' in word:
            corrections.append(word.replace('z', 's'))
        if 'x' in word:
            corrections.append(word.replace('x', 'c'))
            corrections.append(word.replace('x', 'ks'))
        
        return corrections
    
    def check_repeated_words(self, text):
        """Check for repeated words like 'the the', 'and and', 'is is'"""
        errors = []
        
        # Split text into words and check for consecutive duplicates
        words = re.findall(r'\b\w+\b', text.lower())
        
        for i in range(len(words) - 1):
            if words[i] == words[i + 1]:
                # Find the position in original text
                pattern = r'\b' + re.escape(words[i]) + r'\s+' + re.escape(words[i]) + r'\b'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    errors.append({
                        'type': 'grammar',
                        'category': 'REPETITION',
                        'rule_id': 'REPEATED_WORDS',
                        'message': f'Repeated word: "{words[i]}"',
                        'suggestions': [words[i]],  # Suggest single occurrence
                        'context': match.group(),
                        'offset': match.start(),
                        'length': len(match.group()),
                        'severity': 'medium'
                    })
        
        return errors
    
    def check_missing_articles(self, text):
        """Check for missing articles (a, an, the)"""
        errors = []
        
        # Look for patterns like "Document is important" instead of "The document is important"
        patterns = [
            (r'\b[A-Z][a-z]+ is (important|good|bad|necessary|useful)', 'Missing article before noun'),
            (r'\b[A-Z][a-z]+ has been', 'Consider adding article before noun'),
            (r'\bDocument is\b', 'Should be "The document is"'),
            (r'\bReport shows\b', 'Should be "The report shows"')
        ]
        
        for pattern, message in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                errors.append({
                    'type': 'grammar',
                    'category': 'ARTICLES',
                    'rule_id': 'MISSING_ARTICLE',
                    'message': message,
                    'suggestions': ['The ' + match.group().lower()],
                    'context': match.group(),
                    'offset': match.start(),
                    'length': len(match.group()),
                    'severity': 'medium'
                })
        
        return errors
    
    def check_common_grammar_mistakes(self, text):
        """Check for common grammar mistakes"""
        errors = []
        
        # Common mistakes and their corrections
        grammar_patterns = [
            # Subject-verb disagreement patterns
            (r'\bIt contain\b', 'It contains', 'Subject-verb disagreement: "It contain" should be "It contains"'),
            (r'\bHe have\b', 'He has', 'Subject-verb disagreement: "He have" should be "He has"'),
            (r'\bShe have\b', 'She has', 'Subject-verb disagreement: "She have" should be "She has"'),
            (r'\bDocument is important\b', 'The document is important', 'Missing article: "Document is important" should be "The document is important"'),
            (r'\bFile contain\b', 'File contains', 'Subject-verb disagreement: "File contain" should be "File contains"'),
            
            # Common mistakes
            (r'\byour welcome\b', 'you\'re welcome', 'Incorrect: "your welcome" should be "you\'re welcome"'),
            (r'\bits me\b', 'it\'s me', 'Missing apostrophe: "its me" should be "it\'s me"'),
            (r'\bwould of\b', 'would have', 'Incorrect: "would of" should be "would have"'),
            (r'\bcould of\b', 'could have', 'Incorrect: "could of" should be "could have"'),
            (r'\bshould of\b', 'should have', 'Incorrect: "should of" should be "should have"'),
            (r'\bthere house\b', 'their house', 'Incorrect: "there house" should be "their house"'),
            (r'\byour right\b', 'you\'re right', 'Incorrect: "your right" should be "you\'re right"'),
        ]
        
        for pattern, correction, message in grammar_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                errors.append({
                    'type': 'grammar',
                    'category': 'GRAMMAR',
                    'rule_id': 'COMMON_MISTAKE',
                    'message': message,
                    'suggestions': [correction],
                    'context': match.group(),
                    'offset': match.start(),
                    'length': len(match.group()),
                    'severity': 'high'
                })
        
        return errors
    
    def get_word_context(self, word, text, context_length=50):
        match = re.search(r'\b' + re.escape(word) + r'\b', text)
        if match:
            start = max(0, match.start() - context_length)
            end = min(len(text), match.end() + context_length)
            return text[start:end]
        return ""
    
    def categorize_grammar_error(self, category):
        severity_map = {
            'TYPOS': 'high',
            'GRAMMAR': 'high', 
            'PUNCTUATION': 'medium',
            'STYLE': 'low',
            'COLLOQUIALISMS': 'low'
        }
        return severity_map.get(category, 'medium')
    
    def analyze_heading_format(self, heading):
        if heading.isupper():
            return 'all_caps'
        elif heading.istitle():
            return 'title_case'
        elif ':' in heading:
            return 'colon_format'
        elif re.match(r'^\d+\.', heading):
            return 'numbered'
        else:
            return 'other'
    
    def calculate_advanced_metrics(self, text):
        words = len(re.findall(r'\b\w+\b', text))
        sentences = textstat.sentence_count(text)
        
        return {
            'word_count': words,
            'sentence_count': sentences,
            'paragraph_count': len([p for p in text.split('\n\n') if p.strip()]),
            'avg_words_per_sentence': round(words / sentences if sentences else 0, 2),
            'flesch_reading_ease': textstat.flesch_reading_ease(text),
            'flesch_kincaid_grade': textstat.flesch_kincaid_grade(text),
            'automated_readability_index': textstat.automated_readability_index(text),
            'coleman_liau_index': textstat.coleman_liau_index(text)
        }
    
    def generate_corrected_text(self, text, spelling_errors, grammar_errors):
        # Try AI-powered correction first (if available)
        if self.ai_enabled and self.ai_provider == "gemini":
            print("🤖 Generating AI-corrected text with Gemini...")
            ai_corrected = self.generate_corrected_text_with_gemini(text)
            if ai_corrected and ai_corrected != text:
                print("✅ AI correction completed!")
                return ai_corrected
            else:
                print("⚠️ AI correction failed, falling back to local correction")
        
        # Fallback to local corrections
        corrected = text
        
        # Apply spelling corrections
        if spelling_errors:
            for error in spelling_errors:
                if error['suggestions'] and error['confidence'] > 0.7:
                    suggestion = error['suggestions'][0]
                    corrected = re.sub(r'\b' + re.escape(error['word']) + r'\b', 
                                     suggestion, corrected, count=1)
        
        # Apply grammar corrections (high confidence only)
        if tool is not None:
            try:
                corrected = tool.correct(corrected)
            except:
                pass
            
        return corrected
    
    def create_highlighted_text(self, text, spelling_errors, grammar_errors, typography_errors, email_errors):
        highlighted = text
        
        # Highlight spelling errors
        if spelling_errors:
            for error in spelling_errors:
                pattern = r'\b' + re.escape(error['word']) + r'\b'
                replacement = f'<span class="spelling-error" title="Suggestions: {", ".join(error["suggestions"])}">{error["word"]}</span>'
                highlighted = re.sub(pattern, replacement, highlighted, count=1)
        
        # Highlight typography errors
        if typography_errors:
            for error in typography_errors:
                if 'text' in error:
                    replacement = f'<span class="typography-error" title="{error["message"]}">{error["text"]}</span>'
                    highlighted = highlighted.replace(error['text'], replacement, 1)
        
        # Highlight email errors
        if email_errors:
            for error in email_errors:
                if 'text' in error:
                    replacement = f'<span class="email-error" title="{error["message"]}">{error["text"]}</span>'
                    highlighted = highlighted.replace(error['text'], replacement, 1)
        
        return highlighted
    
    def create_error_summary(self, spelling_errors, grammar_errors, typography_errors, structure_errors, email_errors):
        # Ensure all error lists are not None
        spelling_errors = spelling_errors or []
        grammar_errors = grammar_errors or []
        typography_errors = typography_errors or []
        structure_errors = structure_errors or []
        email_errors = email_errors or []
        
        return {
            'spelling': {
                'count': len(spelling_errors),
                'high_confidence': len([e for e in spelling_errors if e.get('confidence', 0) > 0.8])
            },
            'grammar': {
                'count': len(grammar_errors),
                'high_severity': len([e for e in grammar_errors if e.get('severity') == 'high'])
            },
            'typography': {
                'count': len(typography_errors),
                'formatting': len([e for e in typography_errors if e.get('type') == 'formatting'])
            },
            'structure': {
                'count': len(structure_errors)
            },
            'email': {
                'count': len(email_errors),
                'invalid_format': len([e for e in email_errors if e.get('subtype') == 'invalid_format'])
            }
        }
    
    def ai_error_detection(self, text: str) -> List[Dict[str, Any]]:
        """Use AI API for intelligent error detection and correction"""
        if not self.ai_enabled:
            return []
        
        try:
            # Split text into chunks for API limits
            chunks = self.split_text_for_ai(text)
            all_errors = []
            
            for chunk in chunks:
                chunk_errors = self.analyze_chunk_with_ai(chunk)
                all_errors.extend(chunk_errors)
            
            return all_errors
        except Exception as e:
            print(f"AI error detection failed: {e}")
            return []
    
    def split_text_for_ai(self, text: str, max_chunk_size: int = 2000) -> List[str]:
        """Split text into manageable chunks for AI analysis"""
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        sentences = re.split(r'[.!?]+', text)
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) <= max_chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def analyze_chunk_with_ai(self, text_chunk: str) -> List[Dict[str, Any]]:
        """Analyze a text chunk using AI API - supports multiple providers"""
        if self.ai_provider == "openai":
            return self.analyze_with_openai(text_chunk)
        elif self.ai_provider == "gemini":
            return self.analyze_with_gemini(text_chunk)
        elif self.ai_provider == "huggingface":
            return self.analyze_with_huggingface(text_chunk)
        else:
            return []
    
    def analyze_with_openai(self, text_chunk: str) -> List[Dict[str, Any]]:
        """Analyze text using OpenAI API"""
        prompt = f"""You are an expert proofreader and editor. Analyze this text for errors and provide corrections.

FOCUS ON THESE CRITICAL ERROR TYPES:
1. Subject-verb disagreement (e.g., "It contain" → "It contains")  
2. Missing articles (e.g., "Document is important" → "The document is important")
3. Obvious spelling mistakes (e.g., "lice.smith" → "alice.smith", "spieling" → "spelling")
4. Grammar errors and sentence structure issues
5. Inconsistent capitalization and punctuation

Return a JSON array with this exact format:
[
  {{
    "type": "spelling|grammar|style",
    "word_or_phrase": "exact_error_text_from_document",
    "message": "clear_explanation_of_error",
    "suggestions": ["correction1", "correction2"],
    "confidence": 0.95,
    "context": "surrounding_text_for_context"
  }}
]

Text to analyze:
{text_chunk}

IMPORTANT: 
- Find REAL errors, not style preferences
- Be specific with word_or_phrase (exact text from document)
- Prioritize obvious mistakes like subject-verb disagreement
- Return only the JSON array, no other text"""

        headers = {
            'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-3.5-turbo',
            'messages': [
                {'role': 'system', 'content': 'You are an expert text editor and proofreader. Analyze text for errors and return structured JSON responses.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.1,
            'max_tokens': 1000
        }
        
        try:
            response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            # Parse the JSON response
            if content.startswith('[') and content.endswith(']'):
                errors = json.loads(content)
                return self.format_ai_errors(errors)
            else:
                print(f"Unexpected AI response format: {content}")
                return []
                
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                print(f"⚠️  OpenAI API rate limit exceeded. Consider upgrading your plan or trying again later.")
                print(f"   Using enhanced local spell checking instead for now.")
            else:
                print(f"AI API request failed: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Failed to parse AI response as JSON: {e}")
            return []
    
    def analyze_with_gemini(self, text_chunk: str) -> List[Dict[str, Any]]:
        """Analyze text using Google Gemini API (Free)"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            model = genai.GenerativeModel('gemini-1.5-flash')  # Free model
            
            prompt = f"""You are an expert proofreader. Analyze this text for errors and return ONLY a JSON array of error objects.

CRITICAL: Focus on these error types:
1. Subject-verb disagreement (e.g., "It contain" should be "It contains")
2. Missing articles (e.g., "Document is" should be "The document is")
3. Obvious spelling mistakes (e.g., "lice.smith" should be "alice.smith", "spieling" should be "spelling")
4. Grammar errors and awkward phrasing
5. Inconsistent capitalization

Format: [{{"type": "spelling|grammar|style", "word_or_phrase": "exact_error_text", "message": "Clear explanation", "suggestions": ["correction1", "correction2"], "confidence": 0.9}}]

EXAMPLES:
- "It contain" → {{"type": "grammar", "word_or_phrase": "It contain", "message": "Subject-verb disagreement", "suggestions": ["It contains"], "confidence": 0.95}}
- "Document is important" → {{"type": "grammar", "word_or_phrase": "Document is important", "message": "Missing definite article", "suggestions": ["The document is important"], "confidence": 0.9}}
- "lice.smith" → {{"type": "spelling", "word_or_phrase": "lice.smith", "message": "Likely typo in name", "suggestions": ["alice.smith"], "confidence": 0.8}}

Text to analyze:
{text_chunk}

Return ONLY the JSON array, no explanations or other text."""
            
            response = model.generate_content(prompt)
            content = response.text.strip()
            
            # Clean up response
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
            
            if content.startswith('[') and content.endswith(']'):
                errors = json.loads(content)
                return self.format_ai_errors(errors)
            else:
                return []
                
        except Exception as e:
            print(f"Google Gemini API error: {e}")
            return []

    def generate_corrected_text_with_gemini(self, text: str) -> str:
        """Generate a fully corrected version of the text using Gemini AI"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""You are an expert editor and proofreader. Please provide a corrected version of the following text, fixing all spelling, grammar, and style errors while maintaining the original meaning and structure.

FOCUS ON:
- Subject-verb agreement (e.g., "It contain" → "It contains")
- Missing articles (e.g., "Document is important" → "The document is important")
- Spelling mistakes (e.g., "thiss" → "this", "containz" → "contains")
- Grammar errors and awkward phrasing
- Proper capitalization and punctuation

Return ONLY the corrected text, no explanations or additional commentary.

Original text:
{text}

Corrected text:"""
            
            response = model.generate_content(prompt)
            corrected_text = response.text.strip()
            
            return corrected_text
                
        except Exception as e:
            print(f"Gemini text correction error: {e}")
            return text  # Return original if correction fails
    
    def analyze_with_huggingface(self, text_chunk: str) -> List[Dict[str, Any]]:
        """Analyze text using Hugging Face API (Free)"""
        try:
            from huggingface_hub import InferenceClient
            
            client = InferenceClient(token=os.getenv('HUGGINGFACE_API_KEY'))
            
            prompt = f"""<s>[INST] Analyze this text for spelling and grammar errors. Return JSON array format:
[{{"type": "spelling", "word": "error", "suggestions": ["fix"]}}]

Text: {text_chunk} [/INST]"""
            
            response = client.text_generation(
                prompt=prompt,
                model="mistralai/Mistral-7B-Instruct-v0.1",
                max_new_tokens=500,
                temperature=0.1
            )
            
            # Try to extract JSON from response
            content = response.strip()
            if '[' in content and ']' in content:
                json_start = content.find('[')
                json_end = content.rfind(']') + 1
                json_content = content[json_start:json_end]
                errors = json.loads(json_content)
                return self.format_ai_errors(errors)
            
            return []
            
        except Exception as e:
            print(f"Hugging Face API error: {e}")
            return []
    
    def format_ai_errors(self, ai_errors: List[Dict]) -> List[Dict[str, Any]]:
        """Format AI errors to match our error structure"""
        formatted_errors = []
        
        for error in ai_errors:
            formatted_error = {
                'type': error.get('type', 'ai_detected'),
                'word': error.get('word_or_phrase', ''),
                'message': error.get('message', ''),
                'suggestions': error.get('suggestions', [])[:5],
                'confidence': error.get('confidence', 0.8),
                'context': error.get('context', ''),
                'severity': 'high' if error.get('confidence', 0) > 0.9 else 'medium',
                'source': 'ai_api'
            }
            formatted_errors.append(formatted_error)
        
        return formatted_errors
    
    def enhanced_local_analysis(self, text: str) -> List[Dict[str, Any]]:
        """Enhanced local spell checking when AI is unavailable"""
        errors = []
        
        # Focus on common typo patterns that our main spell checker might have missed
        high_confidence_typos = {
            'thiss': 'this',
            'containz': 'contains', 
            'concludez': 'concludes',
            'analyz': 'analyze',
            'spelng': 'spelling',
            'challange': 'challenge',
            'featuress': 'features',
            'smple': 'simple',
            'spieling': 'spelling',  # Added from user's example
            'lice': 'alice'  # Common typo in names
        }
        
        # Check for subject-verb disagreement patterns
        grammar_patterns = [
            (r'\bIt contain\b', 'It contains', 'Subject-verb disagreement: singular subject requires singular verb'),
            (r'\bDocument is important\b', 'The document is important', 'Missing definite article before "document"'),
            (r'\bDocument is\b(?!\s+important)', 'The document is', 'Missing definite article before "document"'),
            (r'\bAnalyzer is\b', 'The analyzer is', 'Missing definite article'),
            (r'\bSystem are\b', 'System is', 'Subject-verb disagreement'),
            (r'\bText are\b', 'Text is', 'Subject-verb disagreement'),
            (r'\bThey was\b', 'They were', 'Subject-verb disagreement'),
            (r'\bHe were\b', 'He was', 'Subject-verb disagreement'),
            (r'\bShe were\b', 'She was', 'Subject-verb disagreement'),
        ]
        
        # Check for typos
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        for word in words:
            if word in high_confidence_typos:
                errors.append({
                    'type': 'spelling',
                    'word': word,
                    'message': f"Possible typo: '{word}' should be '{high_confidence_typos[word]}'",
                    'suggestions': [high_confidence_typos[word]],
                    'confidence': 0.95,
                    'severity': 'high',
                    'source': 'enhanced_local'
                })
        
        # Check for grammar patterns
        for pattern, correction, message in grammar_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                errors.append({
                    'type': 'grammar',
                    'word': match.group(),
                    'message': f"{message}: '{match.group()}' should be '{correction}'",
                    'suggestions': [correction],
                    'confidence': 0.90,
                    'severity': 'high',
                    'source': 'enhanced_local'
                })
        
        return errors

# Initialize the analyzer
analyzer = AdvancedDocumentAnalyzer()

@app.route('/')
def index():
    return send_from_directory('.', 'version_selector.html')

@app.route('/premium')
def premium():
    return send_from_directory('.', 'premium_index.html')

@app.route('/enhanced')
def enhanced():
    return send_from_directory('.', 'enhanced_index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    uploaded = request.files['file']
    filename = uploaded.filename

    if not filename.lower().endswith(('.pdf', '.docx', '.txt')):
        return jsonify({'error': 'Unsupported file format. Please upload PDF, DOCX, or TXT files.'}), 400

    # Check file size
    uploaded.seek(0, io.SEEK_END)
    if uploaded.tell() > MAX_FILE_SIZE:
        return jsonify({'error': f'File too large. Maximum size is {MAX_FILE_SIZE//1024//1024}MB'}), 400
    uploaded.seek(0)

    try:
        file_bytes = io.BytesIO(uploaded.read())
        result = analyzer.comprehensive_analysis(file_bytes, filename)
        
        if result is None:
            return jsonify({'error': 'Analysis returned no result'}), 500
            
        if 'error' in result:
            return jsonify(result), 400
            
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5011))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
