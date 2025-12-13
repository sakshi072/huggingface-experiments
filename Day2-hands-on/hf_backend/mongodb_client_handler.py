from typing import List, Optional, Dict, Any
from pymongo import MongoClient, DESCENDING
from datetime import datetime  # Fixed: removed bson.objectid import
import uuid
from .config import MONGO_DB, logger
from .models import HistoryMessage, ChatSessionMetadata

CHAT_COLLECTION_NAME = "chat-sessions"
CHAT_METADATA_COLLECTION = "chat-metadata"

class MongoChatClient:
    """
    Handles persistence and retrieval of chat history using MongoDB.
    Now supports multi-user architecture with separate chat sessions.

    Collections:
    - chat-sessions: Stores actual messages for each chat
    - chat-metadata: Stores metadata about each chat (title, timestamps, etc.)
    """
    def __init__(self, db: Optional[Any]):
        self.db = db
        if self.db is not None:
            self.collection = self.db[CHAT_COLLECTION_NAME]
            self.metadata_collection = self.db[CHAT_METADATA_COLLECTION]

            try:
                self.metadata_collection.create_index(
                    [("user_id", 1), ("updated_at", DESCENDING)]
                )

                self.metadata_collection.create_index("chat_id", unique=True)
                self.collection.create_index("chat_id", unique=True)

                logger.info(
                    f"MongoDB collections ready: '{CHAT_COLLECTION_NAME}', "
                    f"'{CHAT_METADATA_COLLECTION}' with indexes"
                )
            except Exception as e:
                logger.warning(f"Could not create indexes (may already exist): {e}")
        else:
            self.collection = None
            self.metadata_collection = None
            logger.error("MongoDB is not initialized. History functions will be disabled.")
    
    def _message_to_mongo(self, message: HistoryMessage) -> Dict[str, Any]:
        """Converts Pydantic model to a MongoDB-friendly dictionary."""
        message_dict = message.model_dump(exclude_none=True)
        return message_dict
    
    def _message_from_mongo(self, message_dict: Dict[str, Any]) -> HistoryMessage:
        """Converts a MongoDB document back to a HistoryMessage model."""
        if '_id' in message_dict:
            del message_dict['_id']
        return HistoryMessage(**message_dict)

    def create_chat_session(self, user_id: str, title: str = "New Chat") -> str:
        """
        Creates a new chat session and returns the chat_id.
        
        Args:
            user_id: The user's unique identifier (from Clerk)
            title: The initial title for the chat
            
        Returns:
            The newly created chat_id (UUID)
            
        Raises:
            Exception: If database operation fails
        """
        if self.metadata_collection is None:
            logger.error("Cannot create chat session - metadata collection not initialized")
            return None

        try: 
            chat_id = str(uuid.uuid4())

            metadata = {
                "chat_id": chat_id,
                "user_id": user_id,
                "title": title,
                "created_at": datetime.utcnow(),  # Fixed typo: was "create_at"
                "updated_at": datetime.utcnow(),
                "message_count": 0
            }

            self.metadata_collection.insert_one(metadata)
            logger.info(
                f"Created new chat session: {chat_id[:8]}... "
                f"for user: {user_id[:8]}... with title: '{title}'"
            )
            
            return chat_id
        except Exception as e:
            logger.error(f"Error creating chat session: {e}", exc_info=True)
            return None
    
    def get_user_chat_sessions(self, user_id: str, limit: int = 10, offset: int = 0) -> List[ChatSessionMetadata]:
        """
        Retrieves all chat sessions for a user, sorted by most recent activity.
        
        Args:
            user_id: The user's unique identifier
            
        Returns:
            List of ChatSessionMetadata objects, sorted by updated_at (newest first)
        """
        if self.metadata_collection is None:
            logger.warning("Cannot get chat sessions - metadata collection not initialized")
            return []

        try:
            sessions = list(
                self.metadata_collection.find(
                    {"user_id": user_id},
                    {"_id": 0}
                )
                .sort("updated_at", DESCENDING)
                .skip(offset)
                .limit(limit)
            )

            logger.info(
                f"Retrieved {len(sessions)} chat sessions for user: {user_id[:8]}... "
                f"(limit={limit}, offset={offset})"
            )
            return [ChatSessionMetadata(**session) for session in sessions]

        except Exception as e:
            logger.error(
                f"Error retrieving chat sessions for user {user_id[:8]}...: {e}", 
                exc_info=True
            )
            return []

    def update_chat_metadata(self, chat_id: str, user_id: str):
        """
        Updates the timestamp and increments message count for a chat.
        Called after each successful message exchange.
        
        Args:
            chat_id: The chat session ID
            user_id: The user's unique identifier (for verification)
        """
        if self.metadata_collection is None:
            logger.warning("Cannot update metadata - collection not initialized")
            return
        
        try:
            result = self.metadata_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {
                    "$set": {"updated_at": datetime.utcnow()},
                    "$inc": {"message_count": 2}
                }
            )

            if result.modified_count > 0:
                logger.debug(f"Updated metadata for chat {chat_id[:8]}...")
            else:
                logger.warning(
                    f"No metadata updated for chat {chat_id[:8]}... "
                    "(may not exist or user mismatch)"
                )
        except Exception as e:
            logger.error(f"Error updating chat metadata for {chat_id[:8]}...: {e}")

    def reset_message_count(self, chat_id: str, user_id: str):
        """
        Resets the message count to 0 for a chat (used when clearing history).
        
        Args:
            chat_id: The chat session ID
            user_id: The user's unique identifier (for verification)
        """
        if self.metadata_collection is None:
            return
        
        try:
            self.metadata_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {"$set": {"message_count": 0}}
            )
            logger.debug(f"Reset message count for chat {chat_id[:8]}...")
        except Exception as e:
            logger.error(f"Error resetting message count: {e}")

    def update_chat_title(self, chat_id: str, user_id: str, title: str):
        """
        Updates the title of a chat session.
        
        Args:
            chat_id: The chat session ID
            user_id: The user's unique identifier (for verification)
            title: The new title for the chat
        """
        if self.metadata_collection is None:
            logger.warning("Cannot update title - metadata collection not initialized")
            return

        try:
            result = self.metadata_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {"$set": {"title": title}}
            )

            if result.modified_count > 0:
                logger.info(f"Updated title for chat {chat_id[:8]}... to '{title}'")
            else:
                logger.warning(
                    f"Could not update title for chat {chat_id[:8]}... "
                    "(may not exist or user mismatch)"
                )
                
        except Exception as e:
            logger.error(f"Error updating chat title: {e}", exc_info=True)

    def delete_chat_session(self, chat_id: str, user_id: str):
        """
        Deletes a chat session and all its messages.
        
        Args:
            chat_id: The chat session ID to delete
            user_id: The user's unique identifier (for verification)
        """
        if self.collection is None or self.metadata_collection is None:
            logger.warning("Cannot delete chat - collections not initialized")
            return

        try:
            msg_result = self.collection.delete_one({"chat_id": chat_id})
            meta_result = self.metadata_collection.delete_one({
                "chat_id": chat_id,
                "user_id": user_id
            })

            if meta_result.deleted_count > 0:
                logger.info(
                    f"Deleted chat session {chat_id[:8]}... for user {user_id[:8]}... "
                    f"(messages: {msg_result.deleted_count}, metadata: {meta_result.deleted_count})"
                )
            else:
                logger.warning(
                    f"No chat session found to delete: {chat_id[:8]}... "
                    f"for user {user_id[:8]}..."
                )
                
        except Exception as e:
            logger.error(f"Error deleting chat session: {e}", exc_info=True)
    
    def verify_chat_ownership(self, chat_id: str, user_id: str) -> bool:
        """
        Verifies that a chat belongs to a specific user.
        
        Args:
            chat_id: The chat session ID
            user_id: The user's unique identifier
            
        Returns:
            True if the user owns this chat, False otherwise
        """
        if self.metadata_collection is None:
            logger.warning("Cannot verify ownership - metadata collection not initialized")
            return False
        
        try:
            result = self.metadata_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id
            })

            is_owner = result is not None
            
            if not is_owner:
                logger.warning(
                    f"Ownership verification failed: chat {chat_id[:8]}... "
                    f"does not belong to user {user_id[:8]}..."
                )
            
            return is_owner
        
        except Exception as e:
            logger.error(f"Error verifying chat ownership: {e}", exc_info=True)
            return False

    def get_history(self, chat_id: str, limit: int = 10, offset: int = 0) -> List[HistoryMessage]:
        """
        Retrieves message history for a given chat ID with pagination.
        
        Messages are stored in MongoDB as: [oldest, ..., newest]
        This function returns them in the same order: oldest to newest
        
        Pagination works from the END (newest messages):
        - offset=0, limit=2 -> last 2 messages (newest)
        - offset=2, limit=2 -> skip last 2, get next 2 (older messages)
        
        Args:
            chat_id: The chat session ID
            limit: Maximum number of messages to return
            offset: Number of messages to skip from the END (newest)
        
        Returns:
            List of HistoryMessage objects (oldest to newest in the returned slice)
        """
        if self.collection is None:
            logger.warning("MongoDB collection not available")
            return []

        try:
            document = self.collection.find_one({'chat_id': chat_id})

            if not document or 'messages' not in document:
                return []
            
            all_messages = document['messages']
            total_count = len(all_messages)
            
            end_index = total_count - offset
            start_index = max(0, end_index - limit)
            
            if start_index >= total_count or end_index <= 0:
                return []
            
            sliced_messages = all_messages[start_index:end_index]
            history = [self._message_from_mongo(msg) for msg in sliced_messages]
            
            return history
        
        except Exception as e:
            logger.error(f"MongoDB Error retrieving history for {chat_id}: {e}", exc_info=True)
            return []
    
    def save_messages(self, chat_id: str, messages: List[HistoryMessage]):
        """Appends new messages to the chat history document."""
        if self.collection is None:
            return 

        try: 
            mongo_messages = [self._message_to_mongo(msg) for msg in messages]
            result = self.collection.update_one(
                {"chat_id": chat_id},
                {"$push": {"messages": {"$each": mongo_messages}}},
                upsert=True
            )

            if result.upserted_id:
                logger.info(f"Created new chat document: {chat_id[:8]}...")
            else:
                logger.debug(f"Appended {len(messages)} messages to chat: {chat_id[:8]}...")

        except Exception as e:
            logger.error(f"MongoDB Error saving messages for {chat_id}: {e}")
    
    def clear_history(self, chat_id: str):
        """Removes the entire chat document from the collection."""
        if self.collection is None:
            return 

        try:
            result = self.collection.delete_one({"chat_id": chat_id})
            if result.deleted_count > 0:
                logger.info(f"Successfully deleted chat history for: {chat_id[:8]}...")
            else:
                logger.warning(f"No chat history found to delete for: {chat_id[:8]}...")
        except Exception as e:
            logger.error(f"MongoDB Error clearing history for {chat_id}: {e}")
        
    def get_chat_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about a user's chats (optional utility method)."""
        if self.metadata_collection is None:
            return {}

        try:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {
                    "_id": None,
                    "total_chats": {"$sum": 1},
                    "total_messages": {"$sum": "$message_count"},
                    "oldest_chat": {"$min": "$created_at"},
                    "newest_chat": {"$max": "$updated_at"}
                }}
            ]
            
            result = list(self.metadata_collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                del stats['_id']
                return stats
            else:
                return {
                    "total_chats": 0,
                    "total_messages": 0,
                    "oldest_chat": None,
                    "newest_chat": None
                }
                
        except Exception as e:
            logger.error(f"Error getting chat statistics: {e}")
            return {}


MONGO_CHAT_CLIENT = MongoChatClient(MONGO_DB)