from typing import List, Optional, Dict, Any
from pymongo import MongoClient
from bson.objectid import datetime
import json
import logging 

from .config import MONGO_DB, logger
from .models import HistoryMessage

CHAT_COLLECTION_NAME = "chat-sessions"

class MongoChatClient:
    """
    Handles persistence and retrieval of chat history using MongoDB.
    Each document stores the history for a single chat ID.
    """
    def __init__(self, db: Optional[Any]):
        self.db = db
        if self.db is not None:
            self.collection = self.db[CHAT_COLLECTION_NAME]
            logger.info(f"MongoDB collection '{CHAT_COLLECTION_NAME}' ready.")
        else:
            self.collection = None
            logger.error("MongoDB is not initialized. History functions will be disabled.")
    
    def _message_to_mongo(self, message: HistoryMessage) -> Dict[str, Any]:
        """Converts Pydantic model to a MongoDB-friendly dictionary."""

        message_dict = message.model_dump(exclude_none=True)
        return message_dict
    
    def _message_from_mongo(self, message_dict:Dict[str,Any]) -> HistoryMessage:
        """Converts a MongoDB document back to a HistoryMessage model."""
        if '_id' in message_dict:
            del message_dict['_id']
        return HistoryMessage(**message_dict)

    def get_history(self, chat_id:str) -> List[HistoryMessage]:
        """Retrieves the full message history for a given chat ID."""
        if self.collection is None:
            return []

        try:
            document = self.collection.find_one({'chat_id': chat_id})
            logger.info(document)
            if not document or 'messages' not in document:
                return []
            history = [self._message_from_mongo(msg) for msg in document['messages']]
            # logger.info(f"History till now -----: {history}")
            return history
        
        except Exception as e:
            logger.error(f"MongoDB Error retrieving history for {chat_id}: {e}")
            return []
    
    def save_messages(self, chat_id:str, messages: List[HistoryMessage]):
        """Appends new messages to the chat history document."""
        if self.collection is None:
            return 

        try: 
            mongo_messages = [self._message_to_mongo(msg) for msg in messages ]
            result = self.collection.update_one(
                {"chat_id": chat_id},
                {"$push": {"messages": {"$each": mongo_messages}}},
                upsert=True
            )

            if result.upserted_id:
                logger.info(f"Created new chat session: {chat_id}")
            else:
                logger.debug(f"Appended {len(messages)} messages to chat: {chat_id}")

        except Exception as e:
            logger.error(f"MongoDB Error saving messages for {chat_id}: {e}")
    
    def clear_history(self, chat_id:str):
        """Removes the entire chat document from the collection."""

        if self.collection is None:
            return 

        try:
            result = self.collection.delete_one({"chat_id":chat_id})
            if result.deleted_count >0:
                logger.info(f"Successfully deleted chat history for: {chat_id}")
            else:
                logger.warning(f"No chat history found to delete for: {chat_id}")
        except Exception as e:
            logger.error(f"MongoDB Error clearing history for {chat_id}: {e}")

MONGO_CHAT_CLIENT = MongoChatClient(MONGO_DB)