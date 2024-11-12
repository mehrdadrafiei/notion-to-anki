import csv
import os
import re
from typing import List, Dict
from notion_client import Client
from groq import Groq
from mistralai import Mistral

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID")
ANKI_OUTPUT_FILE = "anki_flashcards.csv"
PROMPT_PREFIX = "Summarize the following text for the back of an Anki flashcard. Provide only the summary, enclosed in [[ ]]: \n"

class ChatBot:
    def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
        raise NotImplementedError

class GroqChatBot(ChatBot):
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
        pattern = r'\[\[(.*?)\]\]'  # This pattern matches text between [[ ]]

        summary = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        content = summary.choices[0].message.content
        
        return re.findall(pattern, content)[0] 

class MistralChatBot(ChatBot):
    def __init__(self, api_key: str):
        self.client = Mistral(api_key=api_key)

    def get_summary(self, prompt: str, model: str = "mistral-large-latest") -> str:
        pattern = r'\[\[(.*?)\]\]'  # This pattern matches text between [[ ]]

        summary = self.client.chat.complete(
            model= model,
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )
        content = summary.choices[0].message.content
        
        return re.findall(pattern, content)[0] 
    
class NotionHandler:
    def get_headings_and_bullets(self, page_id: str):
        raise NotImplementedError

class NotionClientHandler(NotionHandler):
    def __init__(self, api_key: str, page_id: str):
        self.client = Client(auth=api_key)
        self.page_id = page_id
        self.url = self._get_page_url()

    def _get_page_url(self):
        page_content = self.client.pages.retrieve(page_id=self.page_id)
        return page_content["url"]

    def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        blocks = self.client.blocks.children.list(block_id=self.page_id)
        return [
            self._parse_block(block) for block in blocks["results"]
            if block["type"] in ['heading_1', 'heading_2', 'heading_3', 'bulleted_list_item']
        ]

    def _parse_block(self, block):
        block_type = block["type"]
        block_id = block["id"].replace("-", "")

        if block_type in ['heading_1', 'heading_2', 'heading_3']:
            return {
                "type": block_type,
                "text": block[block_type]["text"][0]["text"]["content"],
                "url": f"{self.url}#{block_id}"
            }
        elif block_type == 'bulleted_list_item':
            return {
                "type": 'bullet_point',
                "text": block["bulleted_list_item"]["rich_text"][0]["text"]["content"],
                "url": f"{self.url}#{block_id}"
            }

class FlashcardStorage:
    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file

    def get_existing_flashcards(self):
        existing_flashcards = set()
        if os.path.exists(self.anki_output_file):
            with open(self.anki_output_file, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    existing_flashcards.add(row[0])
        return existing_flashcards

    def save_flashcard(self, front: str, back_with_link: str):
        with open(self.anki_output_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([front, back_with_link])
            print(f"Flashcard with front: '{front}' created!")

class FlashcardCreator:
    def __init__(self, flashcard_storage: FlashcardStorage):
        self.flashcard_storage = flashcard_storage

    def create_flashcards(self, headings_and_bullets: List[Dict[str, str]], chatbot: ChatBot) -> None:
        existing_flashcards = self.flashcard_storage.get_existing_flashcards()
        for item in headings_and_bullets:
            front = item['text']
            if front in existing_flashcards:
                print(f"Skipping already processed flashcard: '{front}'")
                continue  
            
            prompt = f"{PROMPT_PREFIX} {front}"
            back = chatbot.get_summary(prompt)
            back_with_link = f'{back}\n URL: <a href="{item["url"]}">Link</a>'
            self.flashcard_storage.save_flashcard(front, back_with_link)

        print(f"Flashcards created successfully in '{self.flashcard_storage.anki_output_file}'.")

class FlashcardService:
    def __init__(self, notion_handler: NotionHandler, chatbot: ChatBot, flashcard_creator: FlashcardCreator):
        self.notion_handler = notion_handler
        self.chatbot = chatbot
        self.flashcard_creator = flashcard_creator

    def run(self) -> None:
        headings_and_bullets = self.notion_handler.get_headings_and_bullets()
        self.flashcard_creator.create_flashcards(headings_and_bullets, self.chatbot)

def chatbot_factory(api_key: str, chatbot_type: str) -> ChatBot:
    if chatbot_type == "groq":
        return GroqChatBot(api_key)
    elif chatbot_type == "mistral":
        return MistralChatBot(api_key)
    else:
        raise ValueError("Unsupported chatbot type")

def notion_handler_factory(api_key: str, page_id: str) -> NotionHandler:
    return NotionClientHandler(api_key, page_id)

if __name__ == "__main__":
    notion_handler = notion_handler_factory(NOTION_API_KEY, NOTION_PAGE_ID)
    chatbot = chatbot_factory(GROQ_API_KEY, "mistral")
    flashcard_storage = FlashcardStorage(ANKI_OUTPUT_FILE)
    flashcard_creator = FlashcardCreator(flashcard_storage)
    
    service = FlashcardService(notion_handler, chatbot, flashcard_creator)
    service.run()

    print("done!")
