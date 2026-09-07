from .client import BaleClient


def send_message(client: BaleClient, chat_id: int, text: str):
    return client.call("sendMessage", chat_id=chat_id, text=text)
