import csv
import logging
import os
from datetime import datetime
from typing import Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.flashcard import ChatBot, FlashcardCreator, FlashcardService, FlashcardStorage, rate_limit


# Fixtures
@pytest.fixture
def mock_storage():
    storage = Mock(spec=FlashcardStorage)
    storage.get_existing_flashcards.return_value = set()
    storage.anki_output_file = "test_output.csv"
    return storage


@pytest.fixture
def mock_chatbot():
    chatbot = Mock(spec=ChatBot)
    chatbot.get_summary.return_value = "Test summary"
    return chatbot


@pytest.fixture
def mock_notion_handler():
    handler = Mock()
    handler.get_headings_and_bullets.return_value = [
        {"text": "test1", "url": "http://test1.com"},
        {"text": "test2", "url": "http://test2.com"},
    ]
    return handler


@pytest.fixture
def temp_csv_file(tmp_path):
    csv_file = tmp_path / "test_flashcards.csv"
    return str(csv_file)


# FlashcardCreator Tests
class TestFlashcardCreator:
    def test_flashcard_creator_initialization(self, mock_storage):
        creator = FlashcardCreator(mock_storage)
        assert creator.flashcard_storage == mock_storage
        assert hasattr(creator, 'cache')

    def test_validate_flashcard_content(self, mock_storage):
        creator = FlashcardCreator(mock_storage)

        # Test valid cases
        assert creator.validate_flashcard_content("Valid content") == True
        assert creator.validate_flashcard_content("ABC") == True

        # Test invalid cases
        assert creator.validate_flashcard_content("") == False
        assert creator.validate_flashcard_content("ab") == False
        assert creator.validate_flashcard_content("a" * 501) == False
        assert creator.validate_flashcard_content(None) == False
        assert creator.validate_flashcard_content(123) == False

    def test_get_cached_summary(self, mock_storage, mock_chatbot):
        creator = FlashcardCreator(mock_storage)

        # Test first call (cache miss)
        result1 = creator.get_cached_summary("test prompt", mock_chatbot)
        assert result1 == "Test summary"
        mock_chatbot.get_summary.assert_called_once()

        # Test second call (cache hit)
        mock_chatbot.get_summary.reset_mock()
        result2 = creator.get_cached_summary("test prompt", mock_chatbot)
        assert result2 == "Test summary"
        mock_chatbot.get_summary.assert_not_called()

    @pytest.mark.parametrize(
        "test_input,expected",
        [
            ([], 0),  # Empty list
            ([{"text": "test", "url": "http://test.com"}], 1),  # Single item
            ([{"text": "test1", "url": "url1"}, {"text": "test2", "url": "url2"}], 2),  # Multiple items
        ],
    )
    def test_create_flashcards(self, test_input, expected, mock_storage, mock_chatbot):
        creator = FlashcardCreator(mock_storage)
        creator.create_flashcards(test_input, mock_chatbot)
        assert mock_storage.save_flashcard.call_count == expected

    def test_create_flashcards_with_existing_cards(self, mock_storage, mock_chatbot):
        mock_storage.get_existing_flashcards.return_value = {"test1"}
        creator = FlashcardCreator(mock_storage)

        input_data = [
            {"text": "test1", "url": "url1"},  # Should be skipped
            {"text": "test2", "url": "url2"},  # Should be processed
        ]

        creator.create_flashcards(input_data, mock_chatbot)
        assert mock_storage.save_flashcard.call_count == 1


# FlashcardStorage Tests
class TestFlashcardStorage:
    def test_initialization(self, temp_csv_file):
        storage = FlashcardStorage(temp_csv_file)
        assert storage.anki_output_file == temp_csv_file

    def test_get_existing_flashcards_empty_file(self, temp_csv_file):
        storage = FlashcardStorage(temp_csv_file)
        flashcards = storage.get_existing_flashcards()
        assert isinstance(flashcards, set)
        assert len(flashcards) == 0

    def test_get_existing_flashcards(self, temp_csv_file):
        # Create test file with some flashcards
        with open(temp_csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["front1", "back1"])
            writer.writerow(["front2", "back2"])

        storage = FlashcardStorage(temp_csv_file)
        flashcards = storage.get_existing_flashcards()
        assert len(flashcards) == 2
        assert "front1" in flashcards
        assert "front2" in flashcards

    def test_save_flashcard(self, temp_csv_file):
        storage = FlashcardStorage(temp_csv_file)
        storage.save_flashcard("test front", "test back")

        with open(temp_csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0] == ["test front", "test back"]


# FlashcardService Tests
class TestFlashcardService:
    def test_service_initialization(self, mock_notion_handler, mock_chatbot, mock_storage):
        creator = FlashcardCreator(mock_storage)
        service = FlashcardService(mock_notion_handler, mock_chatbot, creator)
        assert service.notion_handler == mock_notion_handler
        assert service.chatbot == mock_chatbot
        assert service.flashcard_creator == creator

    def test_service_run(self, mock_notion_handler, mock_chatbot, mock_storage):
        creator = FlashcardCreator(mock_storage)
        service = FlashcardService(mock_notion_handler, mock_chatbot, creator)

        service.run()

        mock_notion_handler.get_headings_and_bullets.assert_called_once()
        assert mock_storage.save_flashcard.call_count == 2


# Rate Limiter Tests
class TestRateLimiter:
    def test_rate_limit_decorator(self):
        @rate_limit(calls=2, period=1)
        def test_func():
            return datetime.now()

        # Call the function twice in quick succession
        start_time = datetime.now()
        result1 = test_func()
        result2 = test_func()
        end_time = datetime.now()

        # Check that the second call was delayed
        time_diff = (end_time - start_time).total_seconds()
        assert time_diff >= 0.5  # At least half the period


def test_error_handling(mock_storage, mock_chatbot):
    creator = FlashcardCreator(mock_storage)
    mock_chatbot.get_summary.side_effect = Exception("API Error")

    with pytest.raises(Exception):
        creator.get_cached_summary("test prompt", mock_chatbot)


if __name__ == "__main__":
    pytest.main(["-v"])
