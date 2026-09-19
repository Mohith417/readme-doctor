# ai-recruiter  
![GitHub stars](https://img.shields.io/github/stars/your-username/ai-recruiter?style=social)  
![GitHub license](https://img.shields.io/github/license/your-username/ai-recruiter)  
![Docker Pulls](https://img.shields.io/docker/pulls/your-username/ai-recruiter)  
![Node.js CI](https://github.com/your-username/ai-recruiter/actions/workflows/node.yml/badge.svg)

> **Full‑stack AI Recruitment System**  
> Built with Flutter (Dart), Node.js, PostgreSQL, Docker & Docker Compose.

---

## 📌 Problem Statement

Modern hiring teams struggle to manage candidate pipelines, automate resume processing, and analyze hiring metrics at scale. Existing solutions either lack real‑time integration or require costly subscriptions.  
**ai‑recruiter** bridges that gap by combining a cross‑platform mobile/web front‑end with a powerful, AI‑driven back‑end—all containerized for easy deployment.

---

## 🚀 Features

### Candidate Experience
| Feature | Description |
|---------|-------------|
| Live Dashboard | Real‑time status updates and personalized metrics |
| Smart Job Feed | AI‑ranked job listings with one‑click application |
| Instant Notifications | Push/SMS alerts for application updates |
| Profile Management | Auto‑populate CV data, track progress |

### Recruiter Experience
| Feature | Description |
|---------|-------------|
| Unified Kanban Board | Drag‑and‑drop pipeline management |
| AI Resume Parsing | PDF → structured data extraction |
| Culture‑Fit Scoring | NLP‑based alignment with company values |
| Analytics Dashboard | Visual hiring funnels, KPIs, team performance |
| Workflow Automation | Background queue for screening & background checks |

---

## 🛠️ Tech Stack

- **Frontend**: Flutter (Riverpod, GoRouter)
- **Backend**: Node.js / Express (TypeScript)
- **Database**: PostgreSQL (Prisma ORM)
- **Queue**: Redis + BullMQ
- **AI Services**: FastAPI (Python) – resume parsing, culture‑fit
- **Real‑time**: Socket.io
- **API Docs**: Swagger / OpenAPI
- **Containerization**: Docker, Docker Compose
- **CI/CD**: GitHub Actions (Node.js lint, unit tests)

---

## 📋 Prerequisites

| Item | Minimum Version |
|------|-----------------|
| Docker & Docker Compose | 20.10+ |
| Flutter SDK | 3.22+ (stable) |
| Node.js | 20+ |
| Yarn | 1.22+ (or npm) |
| PostgreSQL | 15+ (if you run locally without Docker) |
| Redis | 7+ (if you run locally without Docker) |

---

## ⚙️ Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-username/ai-recruiter.git
cd ai-recruiter
```

### 2️⃣ Set Up Environment Variables

Create a `.env` file at the root of each service folder.

```bash
# api/.env
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_recruiter
REDIS_URL=redis://localhost:6379
JWT_SECRET=super_secret_key

# worker/.env
REDIS_URL=redis://localhost:6379
```

> *Tip:* Use the `.env.example` files as templates.

### 3️⃣ Build & Start Services

```bash
docker compose up -d --build
```

This will spin up:

- PostgreSQL (`ai_recruiter-db`)
- Redis (`ai_recruiter-redis`)
- FastAPI AI services (`ai_res_parser`, `ai_culture_fit`)
- Express API (`api`)
- Flutter front‑end (for web: `flutter run -d chrome`)

### 4️⃣ Run Database Migrations

```bash
docker compose exec api npx prisma migrate deploy
```

> For manual migration, run `npx prisma migrate dev --name init` inside the `api` container.

### 5️⃣ Run Front‑end

```bash
cd frontend
flutter pub get
flutter run -d chrome
```

The web app will be available at `http://localhost:3000`.

---

## 📚 Usage Examples

### A. Apply to a Job (Candidate)

```bash
curl -X POST http://localhost:4000/api/jobs/123/apply \
  -H "Content-Type: application/json" \
  -d '{"candidateId":"c456","resumePdfUrl":"https://..." }'
```

### B. Retrieve Pipeline (Recruiter)

```bash
curl http://localhost:4000/api/pipeline?stage=interview \
  -H "Authorization: Bearer <JWT>"
```

### C. AI Resume Parsing (FastAPI)

```bash
curl -X POST http://localhost:5000/parse-resume \
  -F "file=@/path/to/resume.pdf"
```

Response:
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "skills": ["Flutter", "Node.js", "Docker"],
  "experience": [
    {"company":"ABC Corp","role":"Engineer","years":3}
  ]
}
```

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork** the repo and create a feature branch: `git checkout -b feat/your-feature`.
2. **Write tests** for your changes.
3. **Lint** and **type‑check**:
   ```bash
   yarn lint
   yarn typecheck
   ```
4. **Run tests**: `yarn test` (backend) & `flutter test` (frontend).
5. **Open a pull request**—reference any related issue.

### Coding Style

- **Backend**: ESLint (`eslint-config-airbnb-base`), TypeScript strict mode.
- **Frontend**: `dartfmt`, `flutter analyze`.
- **Docs**: Keep README and comments concise and clear.

### Issue Workflow

- Use labels: `bug`, `feature`, `help-wanted`.
- Provide a clear description, steps to reproduce (for bugs), or expected behavior (for features).

---

## 📄 License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

## 📞 Contact & Support

- **Project Lead** – [@your-github-username](https://github.com/your-username)
- **Discord** – `ai-recruiter#1234`
- **Email** – ai.recruiter@example.com

---

*Happy recruiting!*