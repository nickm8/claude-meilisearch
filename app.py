from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from datetime import datetime
import duckdb
import logging
import traceback
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_PATH = "chat_data.db"
JSON_DIR = "raw_json"
os.makedirs(JSON_DIR, exist_ok=True)

# Initialize database and create table
def init_db():
    try:
        conn = duckdb.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_data (
                uuid VARCHAR PRIMARY KEY,
                collected_at TIMESTAMP,
                json_path VARCHAR,
                chat_data JSON,
                model_name VARCHAR,
                conversation_length INTEGER,
                first_user_message TEXT,
                last_assistant_message TEXT
            )
        """)
        return conn
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def extract_chat_metadata(data):
    try:
        return {
            'model_name': data.get('model', 'unknown'),
            'conversation_length': len(data.get('messages', [])),
            'first_user_message': next((m['content'] for m in data.get('messages', []) 
                                     if m.get('role') == 'user'), None),
            'last_assistant_message': next((m['content'] for m in reversed(data.get('messages', []))
                                          if m.get('role') == 'assistant'), None)
        }
    except Exception as e:
        logger.error(f"Metadata extraction failed: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'model_name': 'unknown',
            'conversation_length': 0,
            'first_user_message': None,
            'last_assistant_message': None
        }

@app.post("/collect")
async def collect_chat_data(request: Request):
    conn = None
    try:
        # Log incoming request
        logger.debug("Received /collect request")
        
        # Get raw JSON data
        raw_data = await request.body()
        logger.debug(f"Raw request body: {raw_data.decode()}")
        
        data = json.loads(raw_data)
        logger.debug(f"Parsed JSON data: {json.dumps(data, indent=2)}")
        
        # Extract the nested data
        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            data = data['data'][0]['data']
        else:
            logger.error("Invalid data structure")
            raise HTTPException(status_code=400, detail="Invalid data structure")
        
        # Extract UUID and add timestamp
        uuid = data.get('uuid')
        if not uuid:
            logger.error("UUID not found in data")
            raise HTTPException(status_code=400, detail="UUID is required")
            
        collected_at = datetime.utcnow()
        
        # Save raw JSON file
        json_filename = f"{uuid}.json"
        json_path = os.path.join(JSON_DIR, json_filename)
        
        logger.debug(f"Saving JSON to {json_path}")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Extract metadata
        metadata = extract_chat_metadata(data)
        logger.debug(f"Extracted metadata: {metadata}")
        
        # Initialize database connection
        conn = init_db()
        
        # Insert into DuckDB
        logger.debug("Inserting data into DuckDB")
        conn.execute("""
            INSERT INTO chat_data (uuid, collected_at, json_path, chat_data, 
                                 model_name, conversation_length, 
                                 first_user_message, last_assistant_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (uuid, collected_at, json_path, json.dumps(data),
              metadata['model_name'], metadata['conversation_length'],
              metadata['first_user_message'], metadata['last_assistant_message']))
        
        return {
            "status": "success",
            "message": f"Data saved with UUID {uuid}",
            "json_path": json_path
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Unexpected error in /collect: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")

@app.get("/search")
async def search_chats(
    query: str = None,
    model: str = None,
    min_length: int = None,
    limit: int = 10
):
    conn = None
    try:
        logger.debug(f"Search request - query: {query}, model: {model}, min_length: {min_length}")
        conn = init_db()
        
        conditions = []
        params = []
        
        if query:
            conditions.append("""
                (first_user_message ILIKE ? OR 
                 last_assistant_message ILIKE ? OR
                 json_extract(chat_data, '$.messages[*].content')::VARCHAR ILIKE ?)
            """)
            query_param = f"%{query}%"
            params.extend([query_param, query_param, query_param])
        
        if model:
            conditions.append("model_name = ?")
            params.append(model)
            
        if min_length:
            conditions.append("conversation_length >= ?")
            params.append(min_length)
            
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        logger.debug(f"Executing search query with where_clause: {where_clause}")
        logger.debug(f"Query parameters: {params}")
        
        results = conn.execute(f"""
            SELECT uuid, collected_at, model_name, conversation_length,
                   first_user_message, last_assistant_message
            FROM chat_data
            WHERE {where_clause}
            ORDER BY collected_at DESC
            LIMIT ?
        """, (*params, limit)).fetchall()
        
        return {"chats": [dict(zip(['uuid', 'collected_at', 'model_name', 'conversation_length',
                                  'first_user_message', 'last_assistant_message'], row))
                         for row in results]}
    
    except Exception as e:
        logger.error(f"Error in /search: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")

@app.get("/chat/{uuid}")
async def get_chat(uuid: str):
    conn = None
    try:
        logger.debug(f"Fetching chat with UUID: {uuid}")
        conn = init_db()
        
        result = conn.execute(
            "SELECT chat_data FROM chat_data WHERE uuid = ?",
            (uuid,)
        ).fetchone()
        
        if not result:
            logger.warning(f"Chat not found with UUID: {uuid}")
            raise HTTPException(status_code=404, detail="Chat not found")
            
        return json.loads(result[0])
    
    except Exception as e:
        logger.error(f"Error in /chat/{uuid}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    logger.debug("Starting application")
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)