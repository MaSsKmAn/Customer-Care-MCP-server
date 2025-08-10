# MCP Multi-Agent Customer Care & Web Search Server
## 📌 Overview
This project is a Multi-Agent MCP Server designed for integration with Puch AI.
It simulates a customer care system and a web search engine, both coordinated by a supervisor agent.
The system also allows a human-in-the-loop for decisions that require manual intervention.

The architecture:

Supervisor Agent → Decides whether a query should be handled by Customer Care Agent or Web Search Agent.

Customer Care Agent → Answers questions related to products, orders, or account help.

Web Search Agent → Performs web searches for user queries.

Human-in-the-loop → Gets involved when the supervisor marks a case as needing manual review.

## ⚙ Features
Multi-Agent Orchestration (Supervisor → Specialized Agents)

Web Search Integration (DuckDuckGo or Google via API)

Customer Care Responses with context

Puch AI MCP Protocol for authentication & tool discovery

Human Approval Mechanism before sending certain responses

Secure HTTPS Deployment ready for Vercel, Cloudflare, or Ngrok

## 📂 File Structure
```
mcp-multi-agent-server/
│── .env.example           # Environment variables template
│── requirements.txt       # Python dependencies
│── README.md              # Project documentation
│── server.py              # MCP server main entry point
│── agents/
│   ├── __init__.py
│   ├── supervisor.py      # Supervisor logic
│   ├── customer_care.py   # Customer care agent
│   ├── web_search.py      # Web search agent
│── utils/
│   ├── __init__.py
│   ├── fetch.py           # HTTP fetching utilities
│   ├── auth.py            # Bearer token authentication
```
## 🔑 Environment Variables
Create a .env file:

```
AUTH_TOKEN=your_secret_token
MY_NUMBER=919876543210
```

## 📦 Installation
Clone the repo
```
git clone https://github.com/your-username/mcp-multi-agent-server.git
cd mcp-multi-agent-server
Install dependencies

pip install -r requirements.txt
Set up environment variables
```

```
cp .env
```
Edit .env with your values
## 🚀 Running Locally

```
python server.py
```
The server will start on:

http://0.0.0.0:8086
## 🌍 Deploying Over HTTPS
For public access, you must serve over HTTPS:

```
ngrok http 8086
Vercel / Cloudflare
```

Deploy as a serverless function.

Ensure .env variables are set in the deployment environment.

## 🔌 Connecting with Puch AI
To connect:
```
/mcp connect https://your-ngrok-or-domain/mcp <AUTH_TOKEN>
```
Example:

```
/mcp connect https://abcd-1234.ngrok.io/mcp mysecrettoken
```

## 🛠 Tools in MCP
validate → Required by Puch AI for authentication.

customer_care → Handles support queries.

web_search → Searches the internet.

supervisor → Routes requests to the right agent or human.

## 📚 Example Workflow
User sends query → MCP server receives it.

Supervisor decides:

"Where is my order?" → Customer Care Agent.

"Latest iPhone reviews" → Web Search Agent.

"Sensitive refund case" → Human approval required.

Response sent back to Puch AI.
## Serer
Deployed on Render:
https://customer-care-mcp-server.onrender.com

## 🤝 Contributing
Pull requests are welcome! Please:

Fork the repo

Create a feature branch

Submit a PR

## 📜 License
MIT License © 2025

