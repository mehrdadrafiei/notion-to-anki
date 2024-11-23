import argparse
import os

from config import settings
from src.chatbots.factory import ChatBotFactory
from src.flashcard import FlashcardCreator, FlashcardService
from src.notion_handler import notion_handler_factory
from src.repositories.FlashcardRepository import CSVFlashcardRepository

NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID")


def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate flashcards from Notion content.')
    parser.add_argument('--output', default="output/flashcards.csv", help='Output path for the flashcards CSV file')
    parser.add_argument('--batch-size', type=int, default=10, help='Number of flashcards to process in one batch')
    return parser.parse_args()


def create_output_directory(output_path: str) -> None:
    """Create output directory if it doesn't exist."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)


def main():
    args = parse_arguments()

    try:
        # Configure output path
        create_output_directory(args.output)

        # Initialize components
        repository = CSVFlashcardRepository(anki_output_file=args.output)
        notion_handler = notion_handler_factory(NOTION_PAGE_ID)
        notion_content = notion_handler.get_headings_and_bullets()
        chatbot = ChatBotFactory.create("groq")

        flashcard_creator = FlashcardCreator(flashcard_repository=repository)

        # Create and run service
        service = FlashcardService(notion_content=notion_content, chatbot=chatbot, flashcard_creator=flashcard_creator)

        print(f"Starting flashcard generation (batch size: {args.batch_size})...")
        service.run()
        print(f"Flashcards have been generated successfully in {args.output}")

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise


if __name__ == "__main__":
    main()
