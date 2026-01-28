import uuid
import time
import threading
import logging
from collections import deque

logger = logging.getLogger(__name__)


class QueueMixin:
    """Custom in-memory queue system with optional DynamoDB persistence."""

    _queues = {}
    _queue_locks = {}
    _queue_master_lock = threading.Lock()

    def _get_queue(self, name):
        with self._queue_master_lock:
            if name not in self._queues:
                self._queues[name] = deque()
                self._queue_locks[name] = threading.Lock()
            return self._queues[name], self._queue_locks[name]

    def create_queue(self, name):
        """Create a named queue."""
        self._get_queue(name)
        logger.info(f"Queue '{name}' created")
        return True

    def send_message(self, name, body):
        """Enqueue a message. Returns message_id."""
        q, lock = self._get_queue(name)
        msg_id = str(uuid.uuid4())
        message = {
            'id': msg_id,
            'body': body,
            'status': 'pending',
            'created_at': time.time(),
            'receive_count': 0,
        }
        with lock:
            q.append(message)
        logger.info(f"Message {msg_id} sent to queue '{name}'")
        return msg_id

    def receive_message(self, name):
        """Dequeue the next pending message. Returns message dict or None."""
        q, lock = self._get_queue(name)
        with lock:
            for msg in q:
                if msg['status'] == 'pending':
                    msg['status'] = 'processing'
                    msg['receive_count'] += 1
                    logger.info(f"Message {msg['id']} received from queue '{name}'")
                    return msg
        return None

    def delete_message(self, name, message_id):
        """Remove a message from the queue by id."""
        q, lock = self._get_queue(name)
        with lock:
            for i, msg in enumerate(q):
                if msg['id'] == message_id:
                    q.remove(msg)
                    logger.info(f"Message {message_id} deleted from queue '{name}'")
                    return True
        return False

    def get_queue_count(self, name):
        """Get count of pending messages in queue."""
        q, lock = self._get_queue(name)
        with lock:
            return sum(1 for msg in q if msg['status'] == 'pending')

    def get_queue_messages(self, name, limit=10):
        """Peek at messages in queue without consuming them."""
        q, lock = self._get_queue(name)
        with lock:
            return list(q)[:limit]

    def purge_queue(self, name):
        """Remove all messages from queue."""
        q, lock = self._get_queue(name)
        with lock:
            q.clear()
        logger.info(f"Queue '{name}' purged")
        return True

    def get_all_queue_status(self):
        """Get status of all queues."""
        result = {}
        with self._queue_master_lock:
            for name in self._queues:
                q = self._queues[name]
                lock = self._queue_locks[name]
                with lock:
                    result[name] = {
                        'total': len(q),
                        'pending': sum(1 for m in q if m['status'] == 'pending'),
                        'processing': sum(1 for m in q if m['status'] == 'processing'),
                    }
        return result
