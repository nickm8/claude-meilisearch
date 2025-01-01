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
        self._last_hash = {}
        print("Indexing handler initialized")
    
    def _get_file_hash(self, file_path):
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _handle_file(self, file_path):
        if not file_path.endswith('.json'):
            return

        current_hash = self._get_file_hash(file_path)
        if self._last_hash.get(file_path) == current_hash:
            return

        print(f"Processing file: {file_path}")
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                documents = [self._clean_document(data)]
            else:
                documents = [self._clean_document(doc) for doc in data]
            
            uuids = [doc['uuid'] for doc in documents if 'uuid' in doc]
            
            if uuids:
                self.index.delete_documents(uuids)
            
            self.index.add_documents(documents)
            self._last_hash[file_path] = current_hash
            print(f"Successfully indexed {len(documents)} documents from {file_path}")
            
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

    def _clean_document(self, doc):
        keys_to_remove = ['settings', 'current_leaf_message_uuid', 'is_starred']
        return {k: v for k, v in doc.items() if k not in keys_to_remove}

    def on_created(self, event):
        if event.is_directory:
            return
        print(f"New file detected: {event.src_path}")
        self._handle_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        print(f"File modified: {event.src_path}")
        self._handle_file(event.src_path)

def setup_meilisearch():
    meili_url = os.getenv("MEILI_URL", "http://localhost:7700")
    master_key = os.getenv("MEILI_MASTER_KEY", "masterKey123")
    print(f"Connecting to Meilisearch at {meili_url}")
    
    retries = 5
    for i in range(retries):
        try:
            client = Client(meili_url, master_key)
            client.health()
            print("Successfully connected to Meilisearch")
            return client
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"Waiting for Meilisearch... ({i + 1}/{retries})")
            time.sleep(5)

def main():
    print("Starting indexer service...")
    data_dir = os.getenv("DATA_DIR", "/app/raw_json")
    index_name = os.getenv("INDEX_NAME", "documents")
    
    print(f"Watching directory: {data_dir}")
    print(f"Using index: {index_name}")
    
    client = setup_meilisearch()
    try:
        client.create_index(index_name, {'primaryKey': 'uuid'})
    except Exception as e:
        print(f"Index already exists or error: {e}")
    
    event_handler = IndexingHandler(client, index_name)
    observer = Observer()
    observer.schedule(event_handler, data_dir, recursive=False)
    
    # Initial indexing of existing files
    print("Performing initial indexing of existing files...")
    for json_file in glob.glob(str(Path(data_dir) / "*.json")):
        print(f"Found existing file: {json_file}")
        event_handler._handle_file(json_file)
    
    observer.start()
    print(f"Watching {data_dir} for changes...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()