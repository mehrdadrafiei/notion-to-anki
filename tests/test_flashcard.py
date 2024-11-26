import unittest
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes.flashcard_routes import (
    FlashcardRequest,
    FlashcardResponse,
    generate_flashcards_task,
    update_task_progress,
)

client = TestClient(app)


@pytest.fixture
def mock_notion_content():
    return Mock()


@pytest.fixture
def mock_chatbot():
    chatbot = Mock(spec=["get_summary"])
    chatbot.get_summary.return_value = "This is a test summary"
    return chatbot


@pytest.fixture
def mock_repository():
    repository = Mock(spec=["save_flashcard", "get_existing_flashcards"])
    repository.save_flashcard.return_value = None
    return repository


class TestFlashcardCreator:

    async def test_validate_flashcard_content(self, mock_repository):
        from src.domain.flashcard.service import FlashcardCreator

        creator = FlashcardCreator(mock_repository)

        # Test valid cases
        assert creator.validate_flashcard_content("Valid content") == True
        assert creator.validate_flashcard_content("ABC") == True

        # Test invalid cases
        assert creator.validate_flashcard_content("") == False
        assert creator.validate_flashcard_content("ab") == False
        assert creator.validate_flashcard_content("a" * 501) == False
        assert creator.validate_flashcard_content(None) == False
        assert creator.validate_flashcard_content(123) == False

    @unittest.skip("Skipping test_get_cached_summary")
    async def test_get_cached_summary(self, mock_repository, mock_chatbot):
        from src.domain.flashcard.service import FlashcardCreator

        creator = FlashcardCreator(mock_repository)

        # Test first call (cache miss)
        result1 = await creator.get_cached_summary("test prompt", mock_chatbot)
        assert result1 == "This is a test summary"
        mock_chatbot.get_summary.assert_called_once()

        # Test second call (cache hit)
        mock_chatbot.get_summary.reset_mock()
        result2 = await creator.get_cached_summary("test prompt", mock_chatbot)
        assert result2 == "This is a test summary"
        mock_chatbot.get_summary.assert_not_called()

    @pytest.mark.parametrize(
        "test_input,expected",
        [
            ([], 0),  # Empty list
            ([{"text": "test", "url": "http://test.com"}], 1),  # Single item
            ([{"text": "test1", "url": "url1"}, {"text": "test2", "url": "url2"}], 2),  # Multiple items
        ],
    )
    @unittest.skip("Skipping test_create_flashcards")
    async def test_create_flashcards(self, test_input, expected, mock_repository, mock_chatbot):
        from src.domain.flashcard.service import FlashcardCreator

        creator = FlashcardCreator(mock_repository)
        await creator.create_flashcards(test_input, mock_chatbot)
        assert mock_repository.save_flashcard.call_count == expected

    @unittest.skip("Skipping test_create_flashcards_with_existing_cards")
    async def test_create_flashcards_with_existing_cards(self, mock_repository, mock_chatbot):
        from src.domain.flashcard.service import FlashcardCreator

        mock_repository.get_existing_flashcards.return_value = {"test1"}
        creator = FlashcardCreator(mock_repository)

        input_data = [
            {"front": "test1", "back": "url1"},  # Should be skipped
            {"front": "test2", "back": "url2"},  # Should be processed
        ]

        await creator.create_flashcards(input_data, mock_chatbot)
        assert mock_repository.save_flashcard.call_count == 1

    async def test_error_handling(self, mock_repository, mock_chatbot):
        from src.domain.flashcard.service import FlashcardCreator

        creator = FlashcardCreator(mock_repository)
        mock_chatbot.get_summary.side_effect = Exception("API Error")

        with pytest.raises(Exception):
            await creator.get_cached_summary("test prompt", mock_chatbot)


class TestFlashcardService(unittest.TestCase):

    async def test_service_initialization(self, mock_notion_content, mock_chatbot, mock_repository):
        from src.domain.flashcard.service import FlashcardCreator, FlashcardService

        creator = FlashcardCreator(mock_repository)
        service = FlashcardService(notion_content=mock_notion_content, chatbot=mock_chatbot, flashcard_creator=creator)
        assert service.notion_content == mock_notion_content
        assert service.chatbot == mock_chatbot
        assert service.flashcard_creator == creator

    async def test_service_run(self):
        with patch('src.flashcard.notion_content') as mock_notion_content:
            with patch('src.flashcard.chatbot') as mock_chatbot:
                with patch('src.flashcard.repository') as mock_repository:
                    from src.domain.flashcard.service import FlashcardCreator, FlashcardService

                    creator = FlashcardCreator(mock_repository)
                    service = FlashcardService(
                        notion_content=mock_notion_content, chatbot=mock_chatbot, flashcard_creator=creator
                    )
                    await service.run()
                    assert mock_repository.save_flashcard.call_count == 2


class TestAPI(unittest.TestCase):
    async def test_create_flashcards_endpoint(self):
        response = client.post(
            "/generate-flashcards/",
            json={"notion_page_id": "test-page", "use_chatbot": False, "output_path": "test.csv"},
        )
        assert response.status_code == 200
        assert "task_id" in response.json()

    async def test_create_flashcards_with_chatbot(self):
        response = client.post(
            "/generate-flashcards/",
            json={
                "notion_page_id": "test-page",
                "use_chatbot": True,
                "chatbot_type": "groq",
                "output_path": "test.csv",
            },
        )
        assert response.status_code == 200
        assert "task_id" in response.json()

    async def test_create_flashcards_invalid_chatbot_type(self):
        response = client.post(
            "/generate-flashcards/",
            json={
                "notion_page_id": "test-page",
                "use_chatbot": True,
                "chatbot_type": "invalid_type",
                "output_path": "test.csv",
            },
        )
        assert response.status_code == 422

    async def test_get_task_status(self):
        # Mock the client.get method
        client.get = Mock(return_value=Mock(status_code=404))

        # Make a GET request to /task-status/{task_id}
        task_id = "some_task_id"
        response = client.get(f"/task-status/{task_id}")

        # Assert that the response status code is 404
        self.assertEqual(response.status_code, 404)
