import csv
from notion_client import Client
from groq import Groq
import os
from typing import List, Dict
import re


NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PAGE_ID = "11e31763-e3a1-80f3-a384-fca2ade6df44"
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

        get_summary = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        content = get_summary.choices[0].message.content
        
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


class FlashcardCreator:
    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file

    def create_flashcards(self, headings_and_bullets: List[Dict[str, str]], chatbot: ChatBot) -> None:
        with open(self.anki_output_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Front', 'Back'])
            for item in headings_and_bullets:
                front = item['text']
                prompt = f"{PROMPT_PREFIX} {front}"
                back = chatbot.get_summary(prompt)
                back_with_link = f'{back}\n URL: <a href="{item["url"]}">Link</a>'
                writer.writerow([front, back_with_link])
                print(f"Flashcard with front: '{front}' created!")

        print(f"Flashcards created successfully in '{self.anki_output_file}'.")


class FlashcardService:
    def __init__(self):
        self.notion_handler = NotionClientHandler(NOTION_API_KEY, PAGE_ID)
        self.chatbot = GroqChatBot(GROQ_API_KEY)
        self.flashcard_creator = FlashcardCreator(ANKI_OUTPUT_FILE)

    def run(self) -> None:
        headings_and_bullets = self.notion_handler.get_headings_and_bullets()
        self.flashcard_creator.create_flashcards(headings_and_bullets, self.chatbot)



if __name__ == "__main__":
    service = FlashcardService()
    service.run()

    print("done!")
