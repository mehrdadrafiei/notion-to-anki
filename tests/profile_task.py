import asyncio

from line_profiler import profile

from api import generate_flashcards_task


# Mock FlashcardRequest class for testing
class FlashcardRequest:
    def __init__(self, notion_page_id, output_path, chatbot_type="default"):
        self.notion_page_id = notion_page_id
        self.output_path = output_path
        self.chatbot_type = chatbot_type


# Mock data for testing
mock_task_id = "test_task_id"
mock_request = FlashcardRequest(notion_page_id="", output_path="output/test_output.csv", chatbot_type="groq")


@profile
def main():
    asyncio.run(generate_flashcards_task(mock_task_id, mock_request))


if __name__ == "__main__":
    main()
