# 📈 InvestTrack

InvestTrack is a modern, full-stack investment tracking application designed to help users manage their portfolios with ease. It features real-time market data, secure authentication, and a responsive, theme-aware user interface.

## 🚀 Live Demo
The application is successfully deployed and live at:
[InvestTrack on Vercel](https://invest-track-4klppuxp7-naylahabdalla-2842s-projects.vercel.app)

---

## 🛠 Tech Stack

### Frontend
- **Framework**: HTML5, Vanilla CSS3, and JavaScript (ES6+).
- **Styling**: [Bootstrap 5.3](https://getbootstrap.com/) for a modern, responsive layout.
- **Features**: 
    - **Dark Mode**: A persistent, user-toggleable dark theme using Bootstrap's color modes and `localStorage`.
    - **Interactive UI**: Clean dashboards with stat cards and hover effects.

### Backend
- **Language**: Python 3.x
- **Framework**: [Flask](https://flask.palletsprojects.com/)
- **API Integration**: [yfinance](https://github.com/ranaroussi/yfinance) for real-time stock and cryptocurrency price fetching.
- **Client**: [Supabase Python SDK](https://supabase.com/docs/reference/python/introduction) for database interactions.

### Database & Security
- **Engine**: [Postgres](https://www.postgresql.org/) (hosted on Supabase).
- **Security**: 
    - **Row Level Security (RLS)**: Fine-grained policies ensure users can only access their own investment records.
    - **Authentication**: Custom signup/login flow with hashed password storage (stored in the `current_hash` column).

---

## 📂 Project Structure

- `app.py`: The main Flask entry point handling routes, authentication, and Supabase integration.
- `templates/`: Jinja2 templates for the various pages (Dashboard, Portfolio, Analytics, etc.).
- `static/`: CSS and static assets.
- `requirements.txt`: Python dependencies for deployment.
- `vercel.json`: Configuration for Vercel's Python runtime and routing.

---

## ⚙️ Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/naylahabdalla/InvestTrack.git
   cd InvestTrack
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Ensure you have your Supabase URL and Key set up. (The application currently uses the Supabase MCP configuration provided during development).

4. **Run the application**:
   ```bash
   python app.py
   ```
   The app will be available at `http://localhost:5000`.

---

## 📜 Deployment

The project is configured for seamless deployment on **Vercel**. 
- The `vercel.json` file uses the `@vercel/python` builder.
- All routes are automatically handled by `app.py`.
- Ensure that your Supabase credentials are added as Environment Variables in the Vercel dashboard.

---

## 🛡 License
© 2025 InvestTrack. All rights reserved.
