import os.path
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/documents']

DOCUMENT_TITLE = 'GigYYC Strategic Business Plan'
MD_FILE_PATH = 'docs/project-summary.md'

def get_credentials():
    """Shows basic usage of the Docs API.
    Prints the title of a sample document.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("ERROR: credentials.json not found.")
                print("Please download your OAuth 2.0 Client credentials from the Google Cloud Console")
                print("and save them as 'credentials.json' in this directory.")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def parse_markdown(file_path):
    """
    Parses a simple markdown file into a list of segments with style info.
    Returns a list of dicts: {'text': str, 'style': str, 'bold': bool}
    Styles: 'TITLE', 'HEADING_1', 'HEADING_2', 'NORMAL', 'LIST_ITEM'
    """
    segments = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_segment = None
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_segment: segments.append(current_segment)
            segments.append({'text': '\n', 'style': 'NORMAL', 'bold': False}) # Blank line
            current_segment = None
            continue

        style = 'NORMAL'
        content = line
        
        # Determine Style
        if line.startswith('# '):
            style = 'TITLE'
            content = line[2:]
        elif line.startswith('## '):
            style = 'HEADING_1'
            content = line[3:]
        elif line.startswith('### '):
            style = 'HEADING_2'
            content = line[4:]
        elif line.startswith('- ') or line.startswith('* '):
            style = 'LIST_ITEM'
            content = '\t' + line[2:] # Indent list items
        
        # Simple Bold parsing within the line (very basic)
        # We will just strip md chars for now to keep it clean, 
        # or implement complex batch requests for inline bolding.
        # For this script, let's keep it simple: whole line bold if it starts/ends with **
        
        is_bold = False
        if content.startswith('**') and content.endswith('**'):
            is_bold = True
            content = content[2:-2]
        
        # Clean up inline bold/italic markers for cleaner text
        content = content.replace('**', '').replace('*', '')

        segments.append({'text': content + '\n', 'style': style, 'bold': is_bold})

    return segments

def create_document(service, title, content_segments):
    # 1. Create a blank document
    body = {'title': title}
    doc = service.documents().create(body=body).execute()
    doc_id = doc.get('documentId')
    print(f'Created document with title: {title}')
    print(f'Document ID: {doc_id}')

    # 2. Build the Batch Requests
    requests = []
    index = 1 # Start index for inserting text
    
    # We must insert text in reverse order if we want to calculate indices easily 
    # OR inserting at the end creates new indices.
    # Actually, inserting at index 1 repeatedly pushes text forward. 
    # But usually, it's better to append.
    # The API documentation says "The index must be less than or equal to the length of the document."
    # A new doc has length 1 (the final newline).
    
    # Strategy: Build a big string and insert it all at once? 
    # No, we want styles.
    # Strategy: Insert text block by block at the END of the document.
    
    current_index = 1
    
    for segment in content_segments:
        text = segment['text']
        style = segment['style']
        
        # Insert Text
        requests.append({
            'insertText': {
                'endOfSegmentLocation': {},
                'text': text
            }
        })
        
        # range for this segment
        start_idx = current_index
        # Reduce end_idx by 1 to effectively select the text content but NOT the trailing newline 
        # (or just to be safe from out-of-bounds at the end of doc).
        # We ensure end_idx > start_idx because pure text segments (non-blank) have len >= 2.
        # Blank lines (len 1) usually don't trigger styling requests below anyway.
        end_idx = current_index + len(text) - 1
        
        # Update Paragraph Style (Heading, etc.)
        p_style = 'NORMAL_TEXT'
        if style == 'TITLE': p_style = 'TITLE'
        elif style == 'HEADING_1': p_style = 'HEADING_1'
        elif style == 'HEADING_2': p_style = 'HEADING_2'
        
        if style != 'NORMAL' and style != 'LIST_ITEM':
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_idx,
                        'endIndex': end_idx
                    },
                    'paragraphStyle': {
                        'namedStyleType': p_style
                    },
                    'fields': 'namedStyleType'
                }
            })
            
#        if style == 'LIST_ITEM':
#             requests.append({
#                'createParagraphBullets': {
#                    'range': {
#                        'startIndex': start_idx,
#                        'endIndex': end_idx
#                    },
#                    'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
#                }
#            })

        # Update Text Style (Bold)
        if segment['bold']:
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_idx,
                        'endIndex': end_idx
                    },
                    'textStyle': {
                        'bold': True
                    },
                    'fields': 'bold'
                }
            })

        current_index += len(text)

    # execute batch update
    if requests:
        service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
        print('Content inserted and formatted.')
        print(f'View your document here: https://docs.google.com/document/d/{doc_id}')

def main():
    creds = get_credentials()
    if not creds:
        return

    service = build('docs', 'v1', credentials=creds)
    
    segments = parse_markdown(MD_FILE_PATH)
    create_document(service, DOCUMENT_TITLE, segments)

if __name__ == '__main__':
    main()
