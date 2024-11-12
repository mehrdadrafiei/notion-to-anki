import csv
import os
from typing import Dict, List

from chatbots import ChatBot, GroqChatBot, MistralChatBot
from notion_handler import NotionClientHandler, NotionHandler

NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID")
ANKI_OUTPUT_FILE = "anki_flashcards.csv"
PROMPT_PREFIX = (
    "Summarize the following text for the back of an Anki flashcard. Provide only the summary, enclosed in [[ ]]: \n"
)


class FlashcardStorage:
    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file

    def get_existing_flashcards(self):
        existing_flashcards = set()
        if os.path.exists(self.anki_output_file):
            with open(self.anki_output_file, mode="r", newline="", encoding="utf-8") as file:
                reader = csv.reader(file)
                for row in reader:
                    existing_flashcards.add(row[0])
        return existing_flashcards

    def save_flashcard(self, front: str, back_with_link: str):
        with open(self.anki_output_file, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([front, back_with_link])
            print(f"Flashcard with front: '{front}' created!")


class FlashcardCreator:
    def __init__(self, flashcard_storage: FlashcardStorage):
        self.flashcard_storage = flashcard_storage

    def create_flashcards(self, headings_and_bullets: List[Dict[str, str]], chatbot: ChatBot) -> None:
        existing_flashcards = self.flashcard_storage.get_existing_flashcards()
        for item in headings_and_bullets:
            front = item["text"]
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


def chatbot_factory(chatbot_type: str) -> ChatBot:
    if chatbot_type == "groq":
        return GroqChatBot()
    elif chatbot_type == "mistral":
        return MistralChatBot()
    else:
        raise ValueError("Unsupported chatbot type")


def notion_handler_factory(page_id: str) -> NotionHandler:
    return NotionClientHandler(page_id)


if __name__ == "__main__":
    notion_handler = notion_handler_factory(NOTION_PAGE_ID)
    chatbot = chatbot_factory("mistral")
    flashcard_storage = FlashcardStorage(ANKI_OUTPUT_FILE)
    flashcard_creator = FlashcardCreator(flashcard_storage)

    service = FlashcardService(notion_handler, chatbot, flashcard_creator)
    service.run()

    print("done!")
