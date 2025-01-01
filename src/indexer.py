import json
import glob
import os
import time
import hashlib
from pathlib import Path
from meilisearch import Client
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class IndexingHandler(FileSystemEventHandler):
    def __init__(self, client, index_name):
        self.client = client
        self.index = client.index(index_name)
        self.pending_updates = set()
        self._last_hash = {}
    
    def _get_file_hash(self, file_path):
        """Calculate MD5 hash of file contents"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _handle_file(self, file_path):
        """Process a single file if it has changed"""
        if not file_path.endswith('.json'):
            return

        current_hash = self._get_file_hash(file_path)
        if self._last_hash.get(file_path) == current_hash:
            return

        print(f"Processing changes in {file_path}")
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Clean and prepare documents
            if isinstance(data, dict):
                documents = [self._clean_document(data)]
            else:
                documents = [self._clean_document(doc) for doc in data]
            
            # Extract UUIDs for deletion
            uuids = [doc['uuid'] for doc in documents if 'uuid' in doc]
            
            # Delete existing documents with these UUIDs
            if uuids:
                self.index.delete_documents(uuids)
            
            # Add updated documents
            self.index.add_documents(documents)
            self._last_hash[file_path] = current_hash
            print(f"Successfully updated {len(documents)} documents from {file_path}")
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    def _clean_document(self, doc):
        """Remove specified keys from document"""
        keys_to_remove = ['settings', 'current_leaf_message_uuid', 'is_starred']
        return {k: v for k, v in doc.items() if k not in keys_to_remove}

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

def setup_meilisearch(url, master_key, index_name):
    """Setup Meilisearch connection and index"""
    client = Client(url, master_key)
    
    # Wait for Meilisearch to be ready
    retries = 5
    for i in range(retries):
        try:
            client.health()
            print("Successfully connected to Meilisearch")
            break
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"Waiting for Meilisearch... ({i + 1}/{retries})")
            time.sleep(5)
    
    # Create index with primary key if it doesn't exist
    try:
        client.create_index(index_name, {'primaryKey': 'uuid'})
    except Exception as e:
        print(f"Index already exists or error creating index: {e}")
    
    return client

def run_auto_indexer():
    # Get configuration from environment variables
    meili_url = os.getenv("MEILI_URL", "http://localhost:7700")
    master_key = os.getenv("MEILI_MASTER_KEY", "masterKey123")
    data_dir = os.getenv("DATA_DIR", "/app/raw_json")
    index_name = os.getenv("INDEX_NAME", "documents")

    # Setup Meilisearch
    client = setup_meilisearch(meili_url, master_key, index_name)
    
    # Create event handler and observer
    event_handler = IndexingHandler(client, index_name)
    observer = Observer()
    observer.schedule(event_handler, data_dir, recursive=False)
    
    # Start watching for changes
    observer.start()
    print(f"Started watching {data_dir} for changes...")
    
    # Initial indexing of existing files
    for json_file in glob.glob(str(Path(data_dir) / "*.json")):
        event_handler._handle_file(json_file)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    run_auto_indexer()