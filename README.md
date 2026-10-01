# getthrulaw

getthrulaw is a Singapore regulatory change monitoring tool. It helps legal and compliance teams find internal documents that may need updating when regulations change.

## Features

- Monitors Singapore Government Gazette updates
- Matches regulatory changes to company documents
- Analyses potential impact and dependencies
- Suggests updates for human review
- Keeps document versions and review history

## Run locally

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

For the Gazette Watch web app:

```bash
python webapp/server.py
```

Then open `http://127.0.0.1:8765`.

## Configuration

Copy `.env.example` to `.env` and add your settings. OpenRouter is optional and disabled by default.

## Tests

```bash
python -m unittest discover -s tests -v
```

This is an assistance tool, not a substitute for legal advice. All suggested changes require human review.
