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
try:
    tool = language_tool_python.LanguageTool('en-US')
    print("LanguageTool initialized successfully")
except Exception as e:
    print(f"Warning: LanguageTool could not be initialized: {e}")
    print("Grammar checking will be disabled")

# Common technical terms and proper nouns to ignore
TECHNICAL_TERMS = set([
    "API", "APIs", "HTTP", "HTTPS", "URL", "URLs", "JSON", "XML", "CSS", "HTML", "PDF", "PDFs",
    "AI", "ML", "IoT", "GPS", "USB", "CPU", "GPU", "RAM", "SSD", "HDD", "OS", "UI", "UX",
    "app", "apps", "email", "emails", "website", "websites", "online", "offline",
    "smartphone", "smartphones", "database", "databases", "username", "usernames",
    "WiFi", "Bluetooth", "login", "logout", "signup", "dropdown", "checkbox"
])

DOMAIN_EXTENSIONS = set([
    "com", "org", "net", "edu", "gov", "mil", "int", "ai", "io", "co", "uk", "ca", "de", "fr"
])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

class AdvancedDocumentAnalyzer:
    def __init__(self):
        self.errors = defaultdict(list)
        
    def extract_text_with_formatting(self, file, filename):
        """Enhanced text extraction preserving structure"""
        text_data = {
            'raw_text': '',
            'paragraphs': [],
            'lines': [],
            'pages': []
        }
        
        if filename.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_data['pages'].append({
                            'page_num': i + 1,
                            'text': page_text,
                            'lines': page_text.split('\n')
                        })
                        text_data['raw_text'] += page_text + "\n\n"
                        
                        # Extract paragraphs (non-empty lines)
                        for line in page_text.split('\n'):
                            line = line.strip()
                            if line:
                                text_data['lines'].append(line)
                                if len(line) > 20:  # Likely a paragraph
                                    text_data['paragraphs'].append(line)
                                    
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
            
        return text_data

    def advanced_spell_check(self, text):
        """Multi-layered spell checking with context awareness"""
        words = re.findall(r'\b\w+\b', text)
        errors = []
        
        for word in words:
            word_lower = word.lower()
            
            # Skip if it's a technical term, URL part, or number
            if (word_lower in TECHNICAL_TERMS or 
                word_lower in DOMAIN_EXTENSIONS or
                word.isdigit() or
                self.is_url_part(word) or
                self.is_email_part(word)):
                continue
                
            # Skip proper nouns (capitalized words that aren't at sentence start)
            if word[0].isupper() and not word.isupper() and len(word) > 2:
                # Check if it's likely a proper noun by context
                if self.likely_proper_noun(word, text):
                    continue
            
            # Multiple spell checker validation
            is_misspelled = False
            suggestions = []
            
            # Check with pyspellchecker
            if word_lower not in spell:
                is_misspelled = True
                suggestions.extend(list(spell.candidates(word))[:3])
            
            # Additional validation with context
            if is_misspelled and len(word) > 2:
                # Special handling for common patterns like double letters
                if self.has_common_misspelling_pattern(word):
                    is_misspelled = True
            
            # Use autocorrect for additional suggestions
            if is_misspelled:
                auto_suggestion = spell_autocorrect(word)
                if auto_suggestion != word and auto_suggestion not in suggestions:
                    suggestions.append(auto_suggestion)
                
                # Add pattern-based suggestions for common mistakes
                pattern_suggestions = self.get_pattern_based_suggestions(word)
                for suggestion in pattern_suggestions:
                    if suggestion not in suggestions:
                        suggestions.append(suggestion)
            
            if is_misspelled and suggestions:
                # Remove duplicates and rank by similarity
                unique_suggestions = list(dict.fromkeys(suggestions))
                ranked_suggestions = sorted(unique_suggestions, 
                                         key=lambda x: fuzz.ratio(word.lower(), x.lower()), 
                                         reverse=True)[:5]
                
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
        errors = []
        
        if tool is None:
            print("Grammar checking is disabled (LanguageTool not available)")
            return errors
        
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
        # Extract text with structure
        text_data = self.extract_text_with_formatting(file, filename)
        
        if not text_data['raw_text'].strip():
            return {'error': 'No readable text found in document'}
        
        # Perform all analyses
        spelling_errors = self.advanced_spell_check(text_data['raw_text'])
        grammar_errors = self.grammar_and_style_check(text_data['raw_text'])
        typography_errors = self.typography_and_formatting_check(text_data)
        structure_errors = self.document_structure_analysis(text_data)
        email_errors = self.email_validation_check(text_data['raw_text'])
        
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
        double_patterns = ['ss', 'll', 'nn', 'mm', 'tt', 'pp']
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
    
    def get_pattern_based_suggestions(self, word):
        """Generate suggestions based on common misspelling patterns"""
        suggestions = []
        word_lower = word.lower()
        
        # For words ending with double letters, try single letter
        if len(word) > 3:
            if word_lower.endswith('ss'):
                candidate = word_lower[:-1]
                if candidate in spell:
                    suggestions.append(candidate)
            if word_lower.endswith('ll'):
                candidate = word_lower[:-1]
                if candidate in spell:
                    suggestions.append(candidate)
        
        # For words with double letters in middle, try single
        double_patterns = ['ss', 'll', 'nn', 'mm', 'tt', 'pp', 'dd', 'ff', 'gg']
        for pattern in double_patterns:
            if pattern in word_lower:
                candidate = word_lower.replace(pattern, pattern[0], 1)
                if candidate in spell and candidate not in suggestions:
                    suggestions.append(candidate)
        
        return suggestions[:3]  # Limit to 3 suggestions
    
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
        corrected = text
        
        # Apply spelling corrections
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
        for error in spelling_errors:
            pattern = r'\b' + re.escape(error['word']) + r'\b'
            replacement = f'<span class="spelling-error" title="Suggestions: {", ".join(error["suggestions"])}">{error["word"]}</span>'
            highlighted = re.sub(pattern, replacement, highlighted, count=1)
        
        # Highlight typography errors
        for error in typography_errors:
            if 'text' in error:
                replacement = f'<span class="typography-error" title="{error["message"]}">{error["text"]}</span>'
                highlighted = highlighted.replace(error['text'], replacement, 1)
        
        # Highlight email errors
        for error in email_errors:
            if 'text' in error:
                replacement = f'<span class="email-error" title="{error["message"]}">{error["text"]}</span>'
                highlighted = highlighted.replace(error['text'], replacement, 1)
        
        return highlighted
    
    def create_error_summary(self, spelling_errors, grammar_errors, typography_errors, structure_errors, email_errors):
        return {
            'spelling': {
                'count': len(spelling_errors),
                'high_confidence': len([e for e in spelling_errors if e['confidence'] > 0.8])
            },
            'grammar': {
                'count': len(grammar_errors),
                'high_severity': len([e for e in grammar_errors if e['severity'] == 'high'])
            },
            'typography': {
                'count': len(typography_errors),
                'formatting': len([e for e in typography_errors if e['type'] == 'formatting'])
            },
            'structure': {
                'count': len(structure_errors)
            },
            'email': {
                'count': len(email_errors),
                'invalid_format': len([e for e in email_errors if e['subtype'] == 'invalid_format'])
            }
        }

# Initialize the analyzer
analyzer = AdvancedDocumentAnalyzer()

@app.route('/')
def index():
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
        
        if 'error' in result:
            return jsonify(result), 400
            
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5011)
