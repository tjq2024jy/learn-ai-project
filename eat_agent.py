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
st.title("AI 美食推荐官 ")
st.caption("使用DeepSeek的AI美食推荐器,通过自动研究并规划好吃的餐厅，开启你的下一次美食之旅。")

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
        name="美食研究员",
        role="根据用户提供的位置搜索附近好吃的餐厅。",
        model=DeepSeek(id="deepseek-v4-pro", api_key=deepseek_api_key),
        description=dedent(
            """\
        你是一位世界级的美食研究员。根据用户提供的位置，生成一系列搜索关键词，
        用于查找相关的餐厅和美食。然后对每个关键词进行网络搜索,分析搜索结果,并返回最相关的10个结果。
        """
        ),
        instructions=[
            "根据用户提供的位置,首先生成3个与该位置相关的搜索词。",
            "对每个搜索词,执行`search_google` 并分析搜索结果。",
            "从所有搜索的结果中,返回与用户偏好最相关的10个结果。尽量包含:店名、菜系、人均价格、评分或口碑。",
            "请记住：结果的质量非常重要。最后用中文总结一下结果，确保内容简洁明了。",
        ],
        tools=[SerpApiTools(api_key=serp_api_key)],
        add_datetime_to_context=True,
    )
    planner = Agent(
    name="美食规划师",
    role="根据用户位置和研究结果生成「吃什么」的完整方案。",
    model=DeepSeek(id="deepseek-v4-pro", api_key=deepseek_api_key),
    description=dedent(
        """\
        你是一位资深美食规划师。根据用户提供的位置、用餐偏好（预算、口味、人数、时间）
        以及一份研究结果列表，生成一份「今天/这几天吃什么」的完整用餐方案。
        """
    ),
    instructions=[
        "根据位置、用户偏好和研究结果，生成一份包含早餐、午餐、晚餐（可选小吃/宵夜）的用餐方案。",
        "每个推荐必须包含：店名或菜名、菜系、大致人均价格、推荐理由。"
        "每餐尽量给出2-3个备选,并标注哪个是「首推」。",
        "如果用户给了预算或口味偏好，务必优先满足。",
        "永远不要编造店名或事实，只能基于研究结果推荐；无法确定的信息要明确说明。",
        "最后用中文输出，结构清晰，用户可以直接照着去吃。",
    ],
    add_datetime_to_context=True,
)


    # Input fields for the user's destination and the number of days they want to travel for
    destination = st.text_input("你想在哪吃?")
    num_budget = st.number_input("你的预算范围是?", min_value=1, max_value=1000, value=20)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("生成美食行程"):
            with st.spinner("寻找中..."):
                # First get research results
                research_results: RunOutput = researcher.run(f"Research {destination} for a {num_budget} day trip", stream=False)

                # Show research progress
                st.write(" 搜索完成 ")
                
            with st.spinner("正在为您创建个性化的美食行程..."):
                # Pass research results to planner
                prompt = f"""
                Destination: {destination}
                Budget: {num_budget}
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