# Flask Query and Document Processing API

This repository contains a Flask application designed for querying and document processing. The application integrates with OpenAI's GPT-3.5-turbo model for handling specific queries and offers functionalities for uploading and processing documents.

## Features

- **Query Interpretation**: Uses OpenAI's GPT-3.5-turbo model to interpret and respond to queries about programming, contract processing, and travel.
- **Contract Processing**: Uses OpenAI's `gpt-3.5-turbo-1106` & `gpt-4-1106-preview` to upload and process documents,
  breaking contracts into `sections` `[{'name':'', 'content': ''}]`.
- **Travel Advice**: Uses OpenAI's `gpt-3.5-turbo`, `gpt-3.5-turbo-1106`, & `dall-e-3` to take a destination,
  give you travel advice, an image, a google map, and several point of interest near the destination
- **CORS Enabled**: Cross-Origin Resource Sharing (CORS) setup for broad accessibility.
- **SSL Support**: Can run HTTPS locally if you have self-signed certs (othrwise remove the line `ssl_context=('cert.pem', 'key.pem')` in the `server.py` file).

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/danielstewart77/GptService.git

## Endpoints
- /query: POST method to submit queries.
- /upload: POST method for file uploads. (This endpoint can be called directly,
  but is also called by the html controls sent to the client when the interpreter believes the user wants to upload files.)
- /: GET method, a simple health check endpoint that returns a happiness message.

## Requirements
- Flask
- Flask-CORS
- python-dotenv
- markdown
- gunicorn
- azure-identity
- azure-keyvault-secrets
- openai
- OpenAI API Key
- Google Maps API Key

## Setup
- Install Dependencies: Use pip install flask flask-cors to install required packages.
- Configure OpenAI Key: Set your OpenAI API key in the environment or as a part of the services configuration.

## Usage
- Starting the Server: Run the application with python app.py. It listens on port 8000 and requires SSL certificates (cert.pem and key.pem).
- Querying: Send POST requests with JSON payload to /query.
- Uploading Files: Send POST requests with a file to /upload.

## Security
- Ensure SSL certificates are correctly set up for secure HTTPS communication.
- Manage CORS settings according to your security requirements.

## Troubleshooting
- Check SSL certificate paths if HTTPS setup fails.
- Ensure the OpenAI API key is correctly configured.

## Contributing
Contributions to enhance the application or add new features are welcome. Please follow standard Git practices for contributions.

## License
MIT
