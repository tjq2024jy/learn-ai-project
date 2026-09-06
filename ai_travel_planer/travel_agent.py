from textwrap import dedent
from agno.agent import Agent
from agno.run.agent import RunOutput
from agno.tools.serpapi import SerpApiTools
import streamlit as st
import re
from agno.models.deepseek import DeepSeek
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
load_dotenv()   # 自动读取项目里的 .env 文件



def generate_ics_content(plan_text:str, start_date: datetime = None) -> bytes:
    """
        Generate an ICS calendar file from a travel itinerary text.

        Args:
            plan_text: The travel itinerary text
            start_date: Optional start date for the itinerary (defaults to today)

        Returns:
            bytes: The ICS file content as bytes
        """
    cal = Calendar()
    cal.add('prodid','-//AI Travel Planner//github.com//' )
    cal.add('version', '2.0')

    if start_date is None:
        start_date = datetime.today()

    # Split the plan into days
    day_pattern = re.compile(r'Day (\d+)[:\s]+(.*?)(?=Day \d+|$)', re.DOTALL)
    days = day_pattern.findall(plan_text)

    if not days: # If no day pattern found, create a single all-day event with the entire content
        event = Event()
        event.add('summary', "Travel Itinerary")
        event.add('description', plan_text)
        event.add('dtstart', start_date.date())
        event.add('dtend', start_date.date())
        event.add("dtstamp", datetime.now())
        cal.add_component(event)  
    else:
        # Process each day
        for day_num, day_content in days:
            day_num = int(day_num)
            current_date = start_date + timedelta(days=day_num - 1)
            
            # Create a single event for the entire day
            event = Event()
            event.add('summary', f"Day {day_num} Itinerary")
            event.add('description', day_content.strip())
            
            # Make it an all-day event
            event.add('dtstart', current_date.date())
            event.add('dtend', current_date.date())
            event.add("dtstamp", datetime.now())
            cal.add_component(event)

    return cal.to_ical()

# Set up the Streamlit app
st.title("AI 旅游规划助手 ")
st.caption("使用DeepSeek的AI旅行规划器,通过自动研究并规划个性化行程，开启你的下一次冒险之旅。")

# Initialize session state to store the generated itinerary
if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

# Get DeepSeek API key from user
deepseek_api_key = st.text_input(
    "输入你的deepseek api key",
    type="password",
    value=os.getenv("DEEPSEEK_API_KEY",""),
)

# Get SerpAPI key from the user
serp_api_key = st.text_input(
    "输入你的Serp API密钥",
    type="password",
    value=os.getenv("SERP_API_KEY",""),
)

if deepseek_api_key and serp_api_key:
    researcher = Agent(
        name="研究员",
        role="根据用户偏好搜索旅游目的地、活动和住宿。",
        model=DeepSeek(id="deepseek-v4-pro", api_key=deepseek_api_key),
        description=dedent(
            """\
        你是一位世界级的旅行研究员。根据用户提供的旅行目的地和旅行天数，生成一系列搜索关键词，
        用于查找相关的旅行活动和住宿。然后对每个关键词进行网络搜索,分析搜索结果,并返回最相关的10个结果。
        """
        ),
        instructions=[
            "根据用户提供的旅行目的地和旅行天数,首先生成3个与该目的地和天数相关的搜索词。",
            "对每个搜索词,执行`search_google` 并分析搜索结果。",
            "从所有搜索的结果中,返回与用户偏好最相关的10个结果。",
            "请记住：结果的质量非常重要。最后用中文总结一下结果，确保内容简洁明了。",
        ],
        tools=[SerpApiTools(api_key=serp_api_key)],
        add_datetime_to_context=True,
    )
    planner = Agent(
        name="规划师",
        role="根据用户偏好和研究结果生成初步行程",
        model=DeepSeek(id="deepseek-v4-pro", api_key=deepseek_api_key),
        description=dedent(
            """\
        你是一位资深旅行规划师。根据用户提供的旅行目的地、旅行天数以及一份研究结果列表，
        你的目标是生成一份符合用户需求和偏好的行程草案。
        """
        ),
        instructions=[
            "根据旅行目的地、用户想要旅行的天数以及研究结果列表，生成一份包含建议活动和住宿的行程草案。",
            "确保行程结构良好、信息丰富且引人入胜。",
            "确保你提供一份细致且平衡的行程，尽可能引用事实。",
            "记住：行程的质量很重要。",
            "专注于清晰度、连贯性和整体质量。",
            "永远不要编造事实或抄袭。始终提供适当的引用。",
        ],
        add_datetime_to_context=True,
    )

    # Input fields for the user's destination and the number of days they want to travel for
    destination = st.text_input("你想去哪里?")
    num_days = st.number_input("你想旅行多少天?", min_value=1, max_value=30, value=7)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("生成行程"):
            with st.spinner("寻找你的目的地中..."):
                # First get research results
                research_results: RunOutput = researcher.run(f"Research {destination} for a {num_days} day trip", stream=False)

                # Show research progress
                st.write(" 搜索完成 ")
                
            with st.spinner("正在为您创建个性化行程..."):
                # Pass research results to planner
                prompt = f"""
                Destination: {destination}
                Duration: {num_days} days
                Research Results: {research_results.content}
                
                Please create a detailed itinerary based on this research.
                """
                response: RunOutput = planner.run(prompt, stream=False)
                # Store the response in session state
                st.session_state.itinerary = response.content
                st.write(response.content)
    
    # Only show download button if there's an itinerary
    with col2:
        if st.session_state.itinerary:
            # Generate the ICS file
            ics_content = generate_ics_content(st.session_state.itinerary)
            
            # Provide the file for download
            st.download_button(
                label="Download Itinerary as Calendar (.ics)",
                data=ics_content,
                file_name="travel_itinerary.ics",
                mime="text/calendar"
            )