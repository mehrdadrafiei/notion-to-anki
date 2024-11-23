import datetime


class Task:
    """Represents a task with its status and history."""

    def __init__(self):
        """Initialize task status and history."""
        self.progress = 0
        self.status = "pending"
        self.message = ""
        self.timestamp = datetime.datetime.now()

    def update_progress(self, progress: int, status: str, message: str):
        """
        Update task progress and status.

        Args:
            progress (int): Current progress percentage
            status (str): Current task status
            message (str): Detailed status message
        """
        self.progress = progress
        self.status = status
        self.message = message

    def to_dict(self):
        """
        Convert task to a dictionary.

        Returns:
            Dict: Task information as a dictionary
        """
        return {
            "progress": self.progress,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }
