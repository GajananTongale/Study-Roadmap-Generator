# app.py
import streamlit as st
import os
import datetime
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pymongo import MongoClient
from youtube_search import YoutubeSearch

load_dotenv()


# MongoDB Setup
class MongoDBClient:
    def __init__(self):
        self.client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.client.study_plans
        self.plans = self.db.plans

    def save_plan(self, plan):
        return self.plans.insert_one(plan).inserted_id

    def update_progress(self, plan_id, topic, completed):
        self.plans.update_one(
            {"_id": plan_id},
            {"$set": {f"progress.{topic}": completed}}
        )

    def get_plan(self, plan_id):
        return self.plans.find_one({"_id": plan_id})


# Gemini Helper
def generate_study_plan(subject, current_level, target_level, hours_per_week):
    prompt_template = """
    Create a detailed {weeks}-week study plan for {subject} from {current_level} to {target_level} level.
    Weekly study hours: {hours_per_week}h. 
    Structure the response as JSON with this format:
    {{
        "weeks": [
            {{
                "week_number": 1,
                "focus_area": "Introduction to X",
                "objectives": ["Objective 1", "Objective 2"],
                "topics": [
                    {{
                        "name": "Topic 1",
                        "hours": 2,
                        "description": "Learning fundamentals..."
                    }}
                ],
                "recommended_hours": 10
            }}
        ]
    }}
    """

    prompt = ChatPromptTemplate.from_template(prompt_template)
    model = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.7)
    chain = prompt | model

    response = chain.invoke({
        "subject": subject,
        "current_level": current_level,
        "target_level": target_level,
        "hours_per_week": hours_per_week,
        "weeks": 4
    })

    return eval(response.content.replace('```json', '').replace('```', ''))


# YouTube Search
def find_youtube_video(query):
    results = YoutubeSearch(query, max_results=1).to_dict()
    if results:
        video = results[0]
        return {
            "id": video["id"],
            "title": video["title"],
            "url": f"https://youtube.com/watch?v={video['id']}",
            "thumbnail": video["thumbnails"][0]
        }
    return None


# Streamlit App
def main():
    st.set_page_config(page_title="StudyPath AI", page_icon="📚", layout="wide")
    mongo = MongoDBClient()

    # Custom CSS
    st.markdown("""
    <style>
        .roadmap {
            display: flex;
            justify-content: space-between;
            padding: 2rem;
            position: relative;
            color:black;
        }
        .roadmap-step {
            flex: 1;
            text-align: center;
            padding: 1rem;
            background: #f0f2f6;
            border-radius: 10px;
            margin: 0 0.5rem;
            position: relative;
            z-index: 2;
            color:black;
        }
        .roadmap-connector {
            position: absolute;
            top: 40%;
            left: 0;
            right: 0;
            height: 4px;
            background: #4CAF50;
            z-index: 1;
            color:black;
        }
        .video-card {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 1rem;
            margin: 1rem 0;
            transition: transform 0.2s;
        }
        .video-card:hover {
            transform: translateY(-5px);
        }
        .progress-bar {
            height: 20px;
            border-radius: 10px;
            background: #e0e0e0;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: #4CAF50;
            transition: width 0.5s ease;
        }
    </style>
    """, unsafe_allow_html=True)

    # Session State
    if 'plan' not in st.session_state:
        st.session_state.plan = None
    if 'progress' not in st.session_state:
        st.session_state.progress = {}

    # Header
    st.title("📚 StudyPath AI - Smart Self-Study Companion")
    st.markdown("---")

    # Input Section
    with st.expander("🚀 Create Your Study Plan", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            subject = st.text_input("📖 Subject/Topic", placeholder="e.g., Machine Learning")
        with col2:
            current_level = st.selectbox("📊 Your Current Level",
                                         ["Beginner", "Intermediate", "Advanced"])
        with col3:
            target_level = st.selectbox("🎯 Target Level",
                                        ["Intermediate", "Advanced", "Expert"])
            hours_per_week = st.slider("⏰ Weekly Study Hours", 1, 40, 10)

        if st.button("✨ Generate Smart Plan"):
            with st.spinner("🧠 Creating your personalized study plan..."):
                try:
                    plan = generate_study_plan(subject, current_level, target_level, hours_per_week)
                    # Add YouTube videos
                    for week in plan['weeks']:
                        for topic in week['topics']:
                            video = find_youtube_video(f"{topic['name']} {subject}")
                            topic['video'] = video

                    # Save to DB
                    plan_id = mongo.save_plan({
                        **plan,
                        "subject": subject,
                        "created_at": datetime.datetime.now(),
                        "progress": {}
                    })

                    st.session_state.plan = {**plan, "_id": plan_id}
                    st.success("🎉 Plan generated successfully!")
                except Exception as e:
                    st.error(f"Error generating plan: {str(e)}")

    # Display Plan
    if st.session_state.plan:
        st.markdown("---")
        st.header("📅 Your Learning Roadmap")

        # Roadmap Visualization
        st.markdown('<div class="roadmap">', unsafe_allow_html=True)
        st.markdown('<div class="roadmap-connector"></div>', unsafe_allow_html=True)
        for week in st.session_state.plan['weeks']:
            with st.container():
                st.markdown(f'''
                <div class="roadmap-step">
                    <h3>Week {week['week_number']}</h3>
                    <p><strong>{week['focus_area']}</strong></p>
                    <p>📅 {week['recommended_hours']} hours</p>
                </div>
                ''', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Progress Tracking
        total_topics = sum(len(w['topics']) for w in st.session_state.plan['weeks'])
        completed = sum(st.session_state.progress.get(t['name'], False)
                        for w in st.session_state.plan['weeks'] for t in w['topics'])
        progress = completed / total_topics if total_topics > 0 else 0

        st.subheader(f"📊 Progress: {progress:.0%}")
        st.markdown(f'''
        <div class="progress-bar">
            <div class="progress-fill" style="width: {progress * 100}%"></div>
        </div>
        ''', unsafe_allow_html=True)

        # Weekly Details
        for week in st.session_state.plan['weeks']:
            with st.expander(f"📆 Week {week['week_number']}: {week['focus_area']}", expanded=True):
                st.markdown(f"**🎯 Objectives:** {', '.join(week['objectives'])}")

                for topic in week['topics']:
                    col1, col2 = st.columns([1, 20])
                    with col1:
                        checked = st.checkbox(
                            "",
                            value=st.session_state.progress.get(topic['name'], False),
                            key=f"check_{topic['name']}"
                        )
                        if checked != st.session_state.progress.get(topic['name'], False):
                            st.session_state.progress[topic['name']] = checked
                            mongo.update_progress(
                                st.session_state.plan['_id'],
                                topic['name'],
                                checked
                            )
                    with col2:
                        with st.container():
                            st.markdown(f"### 📚 {topic['name']}")
                            st.markdown(f"⏳ {topic['hours']} hours | {topic['description']}")

                            if topic.get('video'):
                                st.markdown(f'''
                                <div class="video-card">
                                    <a href="{topic['video']['url']}" target="_blank">
                                        <img src="{topic['video']['thumbnail']}" width="100%">
                                        <p>{topic['video']['title']}</p>
                                    </a>
                                </div>
                                ''', unsafe_allow_html=True)


if __name__ == "__main__":
    main()