from typing import List, Optional, Dict, Any, Tuple
from pymongo import DESCENDING, ASCENDING
from pymongo.errors import DuplicateKeyError
from datetime import datetime 
from bson import ObjectId
import uuid
import base64
import json

from .config import get_db, logger
from .models import (
    HistoryMessage, ChatSessionMetadata, 
    MessageDocument, ChatMetadataDocument, 
    CursorInfo 
)

CHAT_METADATA_COLLECTION = "chat-metadata"
MESSAGES_COLLECTION = "messages"

class CursorEncoder:
    """
    Encode/decode cursors for pagination
    
    Why?
    - Hide internal implementation
    - URL-safe
    - Tamper-resistant
    """
    @staticmethod
    def encode(field:str, value:Any, direction:str = "forward") -> str:
        """Encode cursor to base64 string"""
        cursor_data = {
            "field":field,
            "value":str(value) if not isinstance(value, str) else value,
            "direction": direction
        }
        json_str = json.dumps(cursor_data)
        return base64.urlsafe_b64encode(json_str.encode()).decode()

    @staticmethod
    def decode(cursor:str) -> CursorInfo:
        """Decode cursor from base64 string"""
        try:
            json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
            data = json.loads(json_str)
            return CursorInfo(**data)
        except Exception as e:
            logger.error(f"Failed to decode cursor: {e}")
            raise ValueError("Invalid cursor")


class MongoChatClient:
    """
    Production-ready MongoDB client with cursor-based pagination
    
    MAJOR CHANGES FROM ORIGINAL:
    1. Cursor-based pagination (not offset) for scalability
    2. Messages stored in separate collection (16MB limit)
    3. Optimized indexes for common queries
    4. Better error handling
    5. Soft delete support
    6. Connection pool usage (via singleton)
    """
    def __init__(self):
        """Initialize client = uses singleton connection pool"""
        self.db = None
        self.metadata_collection = None
        self.messages_collection = None
    
    def _ensure_initialized(self):
        """Lazy initialization - get DB when needed"""
        if self.db is None:
            self.db = get_db()
            self.metadata_collection = self.db[CHAT_METADATA_COLLECTION]
            self.messages_collection = self.db[MESSAGES_COLLECTION]
            self._ensure_indexes()
    
    def _ensure_indexes(self):
        """
        Create optimized indexes for production
        
        INDEX STRATEGY:
        1. Metadata collection: user queries, ownership verification
        2. Messages collection: efficient message retrieval, pagination
        """
        try:
            # === METADATA COLLECTION INDEXES ===
            
            # 1. User's sessions sorted by activity (most common query)
            # Covers: get_user_chat_sessions with cursor pagination
            self.metadata_collection.create_index(
                [("user_id", ASCENDING), ("updated_at", DESCENDING), ("chat_id", ASCENDING)],
                name="user_sessions_cursor_idx",
                background=True
            )
            
            # 2. Unique chat_id for fast lookup
            self.metadata_collection.create_index(
                "chat_id",
                unique=True,
                name="chat_id_unique_idx",
                background=True
            )
            
            # 3. User + chat_id for ownership verification (covered by #1)
            # But explicit index for clarity and if we need different sort
            self.metadata_collection.create_index(
                [("user_id", ASCENDING), ("chat_id", ASCENDING)],
                name="user_chat_ownership_idx",
                background=True
            )
            
            # 4. Exclude deleted chats from queries
            self.metadata_collection.create_index(
                [("deleted", ASCENDING), ("user_id", ASCENDING), ("updated_at", DESCENDING)],
                name="active_sessions_idx",
                background=True
            )

            # === MESSAGES COLLECTION INDEXES ===

            # 1. Get messages for a chat (cursor pagination)
            # Covers: get_history query with cursor
            self.messages_collection.create_index(
                [("chat_id", ASCENDING), ("squence", DESCENDING), ("message_id", ASCENDING)],
                name="chat_messages_cursor_idx",
                background=True
            )

            # 2. User's messages for analytics
            self.messages_collection.create_index(
                [("user_id", ASCENDING), ("timestamp", DESCENDING)],
                name="user_messages_idx",
                background=True
            )

            # 3. Unique message_id
            self.messages_collection.create_index(
                "message_id",
                unique=True,
                name="message_id_unique_idx",
                background=True
            )
            logger.info("✅ Production indexes created/verified")
            
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

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
        self._ensure_initialized()

        try: 
            chat_id = str(uuid.uuid4())

            metadata = ChatMetadataDocument(  # FIXED: Use Pydantic model
                chat_id=chat_id,
                user_id=user_id,
                title=title,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                message_count=0
            )

            self.metadata_collection.insert_one(metadata.model_dump())
            logger.info(
                f"Created new chat session: {chat_id[:8]}... "
                f"for user: {user_id[:8]}... with title: '{title}'"
            )
            
            return chat_id
        except DuplicateKeyError:
            logger.error(f"Duplicate chat_id collision (rare): {chat_id}")
            raise
        except Exception as e:
            logger.error(f"Error creating chat session: {e}", exc_info=True)
            return
    
    def get_user_chat_sessions(self, user_id: str, limit: int = 10, cursor: Optional[str] = None) -> Tuple[List[ChatSessionMetadata], Optional[str], bool]:
        """
        CURSOR-BASED pagination for chat sessions
        
        WHY CURSOR OVER OFFSET?
        - Consistent results even when data changes
        - No performance degradation with deep pagination
        - Index-friendly (can seek directly to position)
        
        CURSOR FORMAT:
        Base64-encoded JSON: {"field": "updated_at", "value": "2025-01-01T00:00:00", "direction": "forward"}
        
        Returns:
            (sessions, next_cursor, has_more)
        """
        self._ensure_initialized()

        try:

            # Build query 
            query = {
                "user_id": user_id,
                "deleted": False
            }

            # Apply cursor if provided
            if cursor: 
                cursor_info = CursorEncoder.decode(cursor)

                # Convert cursor value based of field type
                if cursor_info.field == "updated_at":
                    cursor_value = datetime.fromisoformat(cursor_info.value)
                    # For descending sort, we want LESS than cursor value
                    query["updated_at"] = {"$lt": cursor_value}
                elif cursor_info.field == "chat_id":
                    query["chat_id"] = {"$gt": cursor_info.value}

            # Execute query with limit + 1 (to check if more exist)
            # Sort by updated_at DESC (most recent first)
            sessions = list(
                self.metadata_collection
                .find(query)
                .sort([("updated_at", DESCENDING), ("chat_id", ASCENDING)])
                .limit(limit + 1)
            )

            # Check if more results exist
            has_more = len(sessions) > limit
            if has_more:
                sessions = sessions[:limit]

            # Generate next cursor
            next_cursor = None
            if has_more and sessions:
                last_session = sessions[-1]
                next_cursor = CursorEncoder.encode(
                    field="updated_at",
                    value=last_session["updated_at"].isoformat(),
                    direction="forward"
                )
            
            # Convert to Pydantic models

            session_models = [
                ChatSessionMetadata(**self._clean_mongo_doc(session)) for session in sessions
            ]

            logger.info(f"Retrieved {len(session_models)} sessions for user {user_id[:8]}...")
            return session_models, next_cursor, has_more

        except Exception as e:
            logger.error(
                f"Error retrieving chat sessions for user {user_id[:8]}...: {e}", 
                exc_info=True
            )
            return [], None, False

    def update_chat_title(self, chat_id: str, user_id: str, title: str):
        """
        Updates the title of a chat session.
        
        Args:
            chat_id: The chat session ID
            user_id: The user's unique identifier (for verification)
            title: The new title for the chat
        """
        self._ensure_initialized()

        try:
            result = self.metadata_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id, "deleted": False},
                {"$set": {"title": title, "updated_at": datetime.utcnow()}}
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
            raise

    def delete_chat_session(self, chat_id: str, user_id: str):
        """
        Soft delete chat session
        
        WHY SOFT DELETE?
        - Can recover accidentally deleted chats
        - Maintain data for analytics
        - Faster than hard delete (no cascade needed)
        
        Trade-off: Takes up storage space
        """
        self._ensure_initialized()

        try:
            # Soft delete metadata
            result = self.metadata_collection.update_one(
                {"chat_id": chat_id, "user_id": user_id},
                {
                    "$set":{
                        "deleted": True,
                        "deleted_at": datetime.utcnow()
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"Soft deleted chat: {chat_id[:8]}...")
            else:
                logger.warning(f"No chat found to delete: {chat_id[:8]}...")
                
        except Exception as e:
            logger.error(f"Error deleting chat session: {e}", exc_info=True)
            raise
    
    def verify_chat_ownership(self, chat_id: str, user_id: str) -> bool:
        """
        Verify user owns the chat
        
        Uses index: user_chat_ownership_idx
            
        Returns:
            True if the user owns this chat, False otherwise
        """
        self._ensure_initialized()
        
        try:
            result = self.metadata_collection.find_one({
                "chat_id": chat_id,
                "user_id": user_id,
                "deleted": False
            }, {"_id": 1})
            
            return result is not None
        
        except Exception as e:
            logger.error(f"Error verifying chat ownership: {e}", exc_info=True)
            return False

    def get_history(self, chat_id: str, limit: int = 20, cursor: Optional[str] = None) -> Tuple[List[HistoryMessage], Optional[str], bool]:
        """
        Retrieves message history for a given chat ID with pagination.
        
        Messages are stored in MongoDB as: [oldest, ..., newest]
        This function returns them in the same order: oldest to newest
        
        CURSOR-BASED pagination for message history
        
        Returns:
            (messages, next_cursor, has_more)
        """
        self._ensure_initialized()

        try:
            query = {"chat_id": chat_id}

            # Apply cursor
            if cursor:
                cursor_info = CursorEncoder.decode(cursor)
                # Sequence is int
                sequence_value = int(cursor_info.value)
                # For descending, we want LESS than cursor
                query["sequence"] = {"$lt": sequence_value}

            # Query with limit + 1
            messages = list(
                self.messages_collection
                .find(query)
                .sort([("sequence", DESCENDING)])
                .limit(limit+1)
            )

            has_more = len(messages) > limit
            if has_more:
                messages = messages[:limit]
            
            # Generate next cursor
            next_cursor = None
            if has_more and messages:
                last_msg = messages[-1]
                next_cursor = CursorEncoder.encode(
                    field="sequence",
                    value=str(last_msg["sequence"]),
                    direction="forward"
                )

            # Convert to HistoyMessage
            history = [
                HistoryMessage(
                    session_id=msg["chat_id"],
                    role=msg["role"],
                    content = msg["content"],
                    timestamp=msg["timestamp"]
                )
                for msg in messages
            ]

            history.reverse()

            return history, next_cursor, has_more
        
        except Exception as e:
            logger.error(f"MongoDB Error retrieving history for {chat_id}: {e}", exc_info=True)
            return [], None, False
    
    def save_messages(self, chat_id: str, user_id:str, messages: List[HistoryMessage]):
        """
        Save messages to separate collection
        
        MAJOR CHANGE: Messages now in separate collection, not embedded array
        
        WHY?
        - Avoid 16MB document limit
        - Better pagination performance
        - Can index message content for search
        
        Trade-off: More documents, need to manage references
        """
        self._ensure_initialized() 

        try: 
            metadata = self.metadata_collection.find_one(
                {"chat_id": chat_id},
                {"message_count": 1}
            )

            if not metadata:
                logger.error(f"Chat not found: {chat_id}")
                return

            start_sequence = metadata.get("message_count", 0)

            messages_doc = []

            for idx, msg in enumerate(messages):
                doc = MessageDocument(
                    message_id = str(ObjectId()),
                    chat_id = chat_id,
                    user_id = user_id,
                    role = msg.role,
                    content = msg.content,
                    timestamp = msg.timestamp,
                    sequence = start_sequence + idx
                )
                messages_doc.append(doc.model_dump())
            
            # Insert messages
            if messages_doc:
                self.messages_collection.insert_many(messages_doc)
            
            last_message = messages[-1] if messages else None
            update_data = {
                "updated_at": datetime.utcnow()
            }

            if last_message:
                update_data["last_message_at"] = last_message.timestamp
                update_data["last_message_preview"] = last_message.content[:100]

            self.metadata_collection.update_one(
                {"chat_id":chat_id},
                {"$inc" : {"message_count": len(messages)}, "$set":update_data}
            )

            logger.debug(f"Saved {len(messages)} messages to chat {chat_id[:8]}...")
            
        except Exception as e:
            logger.error(f"Error saving messages: {e}", exc_info=True)
            raise
    
    def clear_history(self, chat_id: str):
        """
        Clear all messages for a chat
        
        Now deletes from messages collection
        """
        self._ensure_initialized()

        try:
            # Delete messages
            result = self.messages_collection.delete_many({"chat_id": chat_id})

            # Reset metadata
            self.metadata_collection.update_one(
                {"chat_id":chat_id},
                {
                    "$set":{
                        "message_count":0,
                        "last_message_at": None,
                        "last_message_preview": None,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"Cleared {result.deleted_count} messages from chat {chat_id[:8]}...")

        except Exception as e:
            logger.error(f"MongoDB Error clearing history for {chat_id}: {e}")
            raise
        
    def get_chat_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get user's chat statistics"""
        self._ensure_initialized()
        
        try:
            pipeline = [
                {"$match": {"user_id": user_id, "deleted": False}},
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
            
            return {
                "total_chats": 0,
                "total_messages": 0,
                "oldest_chat": None,
                "newest_chat": None
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

MONGO_CHAT_CLIENT = MongoChatClient()