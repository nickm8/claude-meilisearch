# Claude Meilisearch  

This repository provides a solution for capturing, exporting, and indexing Claude AI conversations using Meilisearch.
Just to make it easier to search on conversation data from Claude.

## Installation  

### Prerequisites  
- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/install/) installed on your system.  

### Setup  
1. Clone this repository:  
   ```bash  
   git clone https://github.com/nickm8/claude-meilsearch.git  
   cd claude-meilsearch  
   ```  

2. Start the services:  
   ```bash  
   docker-compose up --build -d  
   ```  

3. Install the required scripts:  
   - [Claude Chat Data Capture](https://greasyfork.org/en/scripts/522473-claude-chat-data-capture)  
   - [Claude Storage Data Exporter](https://greasyfork.org/en/scripts/522475-claude-storage-data-exporter)  

4. Follow the setup instructions provided with the scripts to configure them for capturing and exporting Claude chat data.  

## Usage  
- Once the system is running, the captured conversations will be indexed automatically.  
- Access Meilisearch on `http://localhost:7700` to interact with the search engine.  

## Environment Variables  
- `MEILI_MASTER_KEY`: Master key for Meilisearch (default: `masterKey123`).  
- Update `.env` file if you need to override default values.  
