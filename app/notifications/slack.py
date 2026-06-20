from typing import Any

import structlog
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.models.work import Work

BlockKitBlock = dict[str, Any]

logger = structlog.get_logger()


class SlackNotifier:
    def __init__(self, bot_token: str, channel_id: str):
        """Initialize the async Slack client."""
        self.client = AsyncWebClient(token=bot_token)
        self.channel_id = channel_id

    async def send(self, vacancy: Work) -> bool:
        """Send a Block Kit message to Slack. Returns True on success."""
        blocks = self._format_block_kit(vacancy)
        fallback_text = f"New Vacancy: {vacancy.title} at {vacancy.company}"

        try:
            response = await self.client.chat_postMessage(  # type: ignore[no-untyped-call]
                channel=self.channel_id,
                text=fallback_text,
                blocks=blocks,
                unfurl_links=False,
            )
            logger.debug("slack_message_sent", vacancy_id=vacancy.id, ts=response["ts"])
            return True
        except SlackApiError as e:
            logger.error("slack_api_error", error=e.response["error"], vacancy_id=vacancy.id)
            return False
        except Exception as e:
            logger.error("slack_unexpected_error", error=str(e), vacancy_id=vacancy.id)
            return False

    def _format_block_kit(self, vacancy: Work) -> list[BlockKitBlock]:
        """Format a vacancy into a Slack Block Kit block array."""
        # Slack header block text limit is 150 chars.
        title = vacancy.title[:145] + "..." if len(vacancy.title) > 150 else vacancy.title

        salary_text = "N/A"
        if vacancy.salary_min and vacancy.salary_max:
            salary_text = f"{vacancy.salary_min} - {vacancy.salary_max} {vacancy.salary_currency}"
        elif vacancy.salary_min:
            salary_text = f"From {vacancy.salary_min} {vacancy.salary_currency}"

        location = vacancy.location or "Remote / N/A"

        blocks: list[BlockKitBlock] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Company:* {vacancy.company}\n*Location:* {location}\n*Salary:* {salary_text}",
                },
            },
        ]

        if vacancy.skills:
            skills_text = ", ".join(vacancy.skills)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Skills:* {skills_text}",
                    },
                }
            )

        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Vacancy",
                            "emoji": True,
                        },
                        "url": vacancy.source_url,
                        "action_id": "view_vacancy_action",
                    }
                ],
            }
        )

        return blocks

    async def close(self) -> None:
        """No-op cleanup kept for interface compatibility with the task's finally block."""
        pass
