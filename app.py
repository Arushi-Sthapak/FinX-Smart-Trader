import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder
import os
import sqlite3
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from dotenv import load_dotenv

# Utility Functions
def calculate_ev(row):
    return (row['Number of equity shares'] * row['Current Price']) + row['Debt'] - row['Cash Equivalents']

def calculate_ev_ebitda(row):
    if row['EBITDA'] != 0:
        return row['Enterprise Value'] / row['EBITDA']
    return None

def calculate_equity_value_per_share(row, scene_growth_multiplier):
    estimated_growth = row['Operating profit growth'] / 100
    estimated_growth *= scene_growth_multiplier
    estimated_ebitda = row['EBITDA'] * (1 + estimated_growth)
    expected_ev = estimated_ebitda * row['EV/EBITDA']
    expected_equity_value = expected_ev - row['Debt']
    if row['Number of equity shares'] <= 0:
        return None
    return expected_equity_value / row['Number of equity shares']

def calculate_ev_ebitda_share_price(df):
    scene_multipliers = [1, 0.8, 0.7, 0.6]
    for index, row in df.iterrows():
        equity_values_per_scene = []
        for multiplier in scene_multipliers:
            equity_value = calculate_equity_value_per_share(row, multiplier)
            if equity_value is not None:
                equity_values_per_scene.append(equity_value)
        if equity_values_per_scene:
            df.loc[index, 'Value as per EV/EBITDA Method'] = sum(equity_values_per_scene) / len(equity_values_per_scene)
        else:
            df.loc[index, 'Value as per EV/EBITDA Method'] = None
    return df

def calculate_revenue_method_share_price(df):
    for index, row in df.iterrows():
        try:
            market_cap = row['Number of equity shares'] * row['Current Price']
            ttm_revenue = row['Sales']
            revenue_multiple = market_cap / ttm_revenue if ttm_revenue != 0 else None
            if revenue_multiple is not None:
                revenue_growth_a = row['Sales growth'] / 100
                estimated_revenue_a = ttm_revenue * (1 + revenue_growth_a)
                expected_mcap_a = estimated_revenue_a * revenue_multiple
                price_per_share_a = expected_mcap_a / row['Number of equity shares']

                revenue_growth_b = revenue_growth_a * 0.9
                estimated_revenue_b = ttm_revenue * (1 + revenue_growth_b)
                expected_mcap_b = estimated_revenue_b * revenue_multiple
                price_per_share_b = expected_mcap_b / row['Number of equity shares']

                df.loc[index, 'Value as per Revenue Method'] = (price_per_share_a + price_per_share_b) / 2
            else:
                df.loc[index, 'Value as per Revenue Method'] = None
        except:
            df.loc[index, 'Value as per Revenue Method'] = None
    return df

def calculate_pe_method_share_price(df):
    for index, row in df.iterrows():
        try:
            ttm_pat = row['Profit after tax'] if pd.notnull(row['Profit after tax']) else 1
            pat_growth = (row['Profit growth'] / 100) if pd.notnull(row['Profit growth']) else 0
            price_to_earning = max(row['Price to Earning'], 1) if pd.notnull(row['Price to Earning']) else 1
            industry_pe = max(row['Industry PE'], 1) if pd.notnull(row['Industry PE']) else 1
            num_equity_shares = row['Number of equity shares'] if pd.notnull(row['Number of equity shares']) else 1

            estimated_pat_a = ttm_pat * (1 + pat_growth)
            expected_mcap_a = estimated_pat_a * price_to_earning
            price_per_share_a = expected_mcap_a / num_equity_shares

            pat_growth_b = pat_growth * 0.7
            estimated_pat_b = ttm_pat * (1 + pat_growth_b)
            expected_mcap_b = estimated_pat_b * price_to_earning
            price_per_share_b = expected_mcap_b / num_equity_shares

            estimated_pat_c = ttm_pat * (1 + pat_growth)
            expected_mcap_c = estimated_pat_c * industry_pe
            price_per_share_c = expected_mcap_c / num_equity_shares

            pat_growth_d = pat_growth * 0.7
            estimated_pat_d = ttm_pat * (1 + pat_growth_d)
            expected_mcap_d = estimated_pat_d * industry_pe
            price_per_share_d = expected_mcap_d / num_equity_shares

            final_value_pe = (
                (price_per_share_a * 0.2) +
                (price_per_share_b * 0.2) +
                (price_per_share_c * 0.3) +
                (price_per_share_d * 0.3)
            )

            df.loc[index, 'Value as per PE Multiple'] = final_value_pe
        except Exception as e:
            df.loc[index, 'Value as per PE Multiple'] = None
    return df

def calculate_pb_method_share_price(df):
    for index, row in df.iterrows():
        try:
            price_to_book = max(row['Price to book value'], 1) if pd.notnull(row['Price to book value']) else 1
            industry_pb = max(row['Industry PBV'], 1) if pd.notnull(row['Industry PBV']) else 1
            book_value_2yr_back = max(row['Book value preceding year'], 1) if pd.notnull(row['Book value preceding year']) else 1
            book_value = max(row['Book value'], 1) if pd.notnull(row['Book value']) else 1

            if price_to_book == 1 or industry_pb==1 or book_value_2yr_back==1 or book_value==1:
                PB_elements_is_1 = "yes"
            else:
                PB_elements_is_1 = "no"

            growth_in_book_value_a = ((book_value / book_value_2yr_back)**0.5 - 1) * 100
            growth_in_book_value_b = growth_in_book_value_a * 0.8
            growth_in_book_value_c = growth_in_book_value_a
            growth_in_book_value_d = growth_in_book_value_c * 0.8

            expected_book_value_a = book_value * (1 + growth_in_book_value_a / 100)
            expected_book_value_b = book_value * (1 + growth_in_book_value_b / 100)
            expected_book_value_c = book_value * (1 + growth_in_book_value_c / 100)
            expected_book_value_d = book_value * (1 + growth_in_book_value_d / 100)

            expected_market_price_a = expected_book_value_a * price_to_book
            expected_market_price_b = expected_book_value_b * price_to_book
            expected_market_price_c = expected_book_value_c * industry_pb
            expected_market_price_d = expected_book_value_d * industry_pb

            final_expected_market_price_a = expected_market_price_a * 0.3
            final_expected_market_price_b = expected_market_price_b * 0.3
            final_expected_market_price_c = expected_market_price_c * 0.2
            final_expected_market_price_d = expected_market_price_d * 0.2

            average_market_price_per_share = (
                final_expected_market_price_a +
                final_expected_market_price_b +
                final_expected_market_price_c +
                final_expected_market_price_d
            )

            df.loc[index, 'Value as per PB Multiple'] = average_market_price_per_share
            df.loc[index, 'PB_elements_is_1'] = PB_elements_is_1
        except Exception as e:
            df.loc[index, 'Value as per PB Multiple'] = None
            st.warning(f"Error processing row, for company {df.loc[index, 'Name']}: {e}")
    return df

def calculate_gain_percentage(df):
    for index, row in df.iterrows():
        try:
            gain = ((
                0.25 * row['Value as per PE Multiple'] +
                0.25 * row['Value as per EV/EBITDA Method'] +
                0.25 * row['Value as per Revenue Method'] +
                0.25 * row['Value as per PB Multiple']
            ) - row['Current Price']) / row['Current Price'] * 100

            df.loc[index, 'Gain%'] = gain
            df.loc[index, 'Final expected price'] = (
                0.25 * row['Value as per PE Multiple'] +
                0.25 * row['Value as per EV/EBITDA Method'] +
                0.25 * row['Value as per Revenue Method'] +
                0.25 * row['Value as per PB Multiple']
            )
        except Exception as e:
            print(f"Error calculating gain for row {index}: {e}")
            df.loc[index, 'Gain%'] = None 
            df.loc[index, 'Final expected price'] = None 
    return df

# Streamlit App
st.set_page_config(page_title="Financial Dashboard & Portfolio Analysis", layout="wide", page_icon="📈")
st.title("Financial Analysis & Portfolio Management")

# Tabs for functionality
tabs = st.tabs(["Financial Dashboard", "Portfolio Analysis"])


# Load environment variables
load_dotenv()
USERNAME = os.getenv("SCRAPER_USERNAME", "default_username")
PASSWORD = os.getenv("SCRAPER_PASSWORD", "default_password")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver-win64\\chromedriver.exe")

def init_driver(download_dir):
    options = Options()
    prefs = {"download.default_directory": download_dir}
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--no-sandbox")
    options.add_argument("--headless")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
    return driver

def download_file_from_screener_with_login(url, download_dir):
    driver = init_driver(download_dir)
    try:
        driver.get("https://www.screener.in/login/")
        wait = WebDriverWait(driver, 10)

        # Input credentials
        username_field = wait.until(lambda d: d.find_element(By.NAME, "username"))
        username_field.send_keys(USERNAME)

        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(PASSWORD)

        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        time.sleep(3)  # Allow login

        # Navigate to the target URL
        driver.get(url)
        time.sleep(3)  # Allow page load

        # Trigger file download
        download_button = wait.until(
            lambda d: d.find_element(By.XPATH, "//button[contains(@class, 'tooltip-left')]")
        )
        download_button.click()
        time.sleep(5)  # Wait for download

        # Return downloaded file path
        downloaded_files = [f for f in os.listdir(download_dir) if f.endswith(".csv")]
        if downloaded_files:
            return os.path.join(download_dir, downloaded_files[0])
        else:
            raise FileNotFoundError("Failed to download the file.")
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None
    finally:
        driver.quit()

# Function to configure AgGrid table
def configure_aggrid(df):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        wrapHeaderText=True,  # Wrap text in headers
        autoHeaderHeight=True,  # Adjust row height automatically
        resizable=True,  # Allow column resizing
        filterable=True,  # Disable filtering (optional)
        sortable=True  # Allow sorting
    )
    # Set specific column widths
    gb.configure_column("Name", filter="agTextColumnFilter", floatingFilter=True, width=90)
    gb.configure_column("Market Capitalisation", width=135)
    gb.configure_column("Current Price", width=100)
    gb.configure_column("Final expected price", width=120)
    gb.configure_column("Gain%", width=100)
    gb.configure_column("Value as per EV/EBITDA Method", width=140)
    gb.configure_column("Value as per Revenue Method", width=140)
    gb.configure_column("Value as per PE Multiple", width=140)
    gb.configure_column("Value as per PB Multiple", width=140)
    gb.configure_column("PB_elements_is_1", width=90)
    gb.configure_grid_options(
        suppressHorizontalScroll=True,  # Prevent horizontal scrolling
        domLayout='autoHeight',  # Adjust table height dynamically
        pagination=True,  # Enable pagination
        paginationPageSize=10  # Show only 10 rows per page
    )
    grid_options = gb.build()
    return grid_options

# Process Data Function
def process_financial_data(input_file):
    try:
        data = pd.read_csv(input_file)
        data['EBITDA'] = data['Operating profit']
        data['Market Capitalisation'] = data['Market Capitalization']
        data['Enterprise Value'] = data.apply(calculate_ev, axis=1)
        data['EV/EBITDA'] = data.apply(calculate_ev_ebitda, axis=1)
        data = calculate_ev_ebitda_share_price(data)
        data = calculate_revenue_method_share_price(data)
        data= calculate_pe_method_share_price(data)
        data = calculate_pb_method_share_price(data)
        data = calculate_gain_percentage(data)
        return data
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None

# Function to convert dataframe to CSV and return as a download link
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')


def financial_health_summary(row):
    # Create a dictionary for quick summary
    summary = {
        "SME": "Yes" if row['Is SME'] == 1 else "No",
        "Market Capitalisation": f"{row['Market Capitalization']:,}",
        "Promoters Holding%": f"{row['Promoter holding']/100:.2%}",
        "Change in PM": f"{row['Change in promoter holding']:.2f}",
        "Change in FII Hold%": f"{row['Change in FII holding']/100:.2%}",
        "Change in DII Hold%": f"{row['Change in DII holding']/100:.2%}",
        "Cash Conversion Cycle": f"{row['Cash Conversion Cycle']:.2f}",
        "Price to Book Value%": f"{row['Price to book value']/100:.2%}",
        "ROE%": f"{row['Return on equity']/100:.2%}",
        "ROCE%": f"{row['Return on capital employed']/100:.2%}",
        "ROIC%": f"{row['Return on invested capital']/100:.2%}",
        "QOQ Sales%": f"{row['QoQ Sales']/100:.2%}",
        "QOQ Profit%": f"{row['QoQ Profits']/100:.2%}",
        "Net Profit (Latest Quarter)": f"{row['Net Profit latest quarter']:,}",
        "Net Profit (3 Quarters Back)": f"{row['Net profit 3quarters back']:,}",
        "OPM%": f"{row['OPM']/100:.2%}",
        "YOY Sales%": f"{row['YOY Quarterly sales growth']/100:.2%}",
        "YOY Profit%": f"{row['YOY Quarterly profit growth']/100:.2%}"
    }

    return pd.DataFrame([summary])


def display_financial_health_summary(df):
    st.markdown("## A Quick Look Into the Financial Health of the Company")

    if isinstance(df, pd.Series):
        df = df.to_frame().T  # Convert Series to DataFrame

    for index, row in df.iterrows():
        summary = financial_health_summary(row)
        st.subheader(f"{row['Name']}")
        # Use st.columns for layout
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(label="SME", value=summary['SME'].iloc[0]) # Or st.metric(label="SME", value=summary['SME'][0]) or st.metric(label="SME", value=summary['SME'].to_string())
            st.metric(label="Market Capitalisation", value=summary['Market Capitalisation'].to_string())
            st.metric(label="Promoters Holding%", value=summary['Promoters Holding%'].iloc[0])
        with col2: 
            st.metric(label="Change in PM", value=summary['Change in PM'].iloc[0])
            st.metric(label="Cash Conversion Cycle", value=summary['Cash Conversion Cycle'].iloc[0])
            st.metric(label="ROE%", value=summary['ROE%'].iloc[0])


        with col3:
            st.metric(label="Change in FII Hold%", value=summary['Change in FII Hold%'].iloc[0])
            st.metric(label="Change in DII Hold%", value=summary['Change in DII Hold%'].iloc[0])
            st.metric(label="Price to Book Value%", value=summary['Price to Book Value%'].iloc[0])
        
        with col4:
            st.metric(label="ROCE%", value=summary['ROCE%'].iloc[0])
            st.metric(label="QOQ Sales%", value=summary['QOQ Sales%'].iloc[0])
            st.metric(label="YOY Profit%", value=summary['YOY Profit%'].iloc[0])


        # Add spacing between companies
        st.markdown("<hr>", unsafe_allow_html=True)

# Ensure directory exists
UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(UPLOAD_DIR, "meta.db")

# Initialize session state if not exists
if 'uploaded_file' not in st.session_state:
    st.session_state['uploaded_file'] = None

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS file_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT,
                        upload_time TEXT)''')
    conn.commit()

# Save file and update metadata
# Save file and update metadata
def save_uploaded_file(uploaded_file):
    st.session_state['uploaded_file'] = uploaded_file

# def save_uploaded_file(uploaded_file):
#     file_path = os.path.join(UPLOAD_DIR, "financial_data.csv")
#     with open(file_path, "wb") as f:
#         f.write(uploaded_file.getbuffer())
    
    # Save metadata
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM file_metadata")  # Keep only last entry
        cursor.execute("INSERT INTO file_metadata (filename, upload_time) VALUES (?, ?)",("financial_data.csv", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

# Get last upload time
def get_last_upload_time():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT upload_time FROM file_metadata ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
    return row[0] if row else "No file uploaded yet"

# Initialize DB
init_db()


# Tab 1: Financial Dashboard (Existing functionality)
with tabs[0]:
    st.header("Financial Dashboard")
    st.write("This section contains your existing functionality.")
    # Include your existing code here
    # Display last uploaded file timestamp
    last_upload_time = get_last_upload_time()
    st.write(f"**Last Uploaded File:** {last_upload_time}")

    uploaded_file = st.file_uploader("Upload Stock Data (CSV)", type="csv")
    scraping_url = st.text_input("Enter the Screener.in URL:", "https://www.screener.in/screens/2284718/all-stocks-download/")
    if st.button("Scrape Data", key="scrape-button"):
        download_dir = os.getcwd()
        with st.spinner("Scraping data..."):
            downloaded_file = download_file_from_screener_with_login(scraping_url, download_dir)
            if downloaded_file:
                st.success("Data scraped successfully.")
                with open(downloaded_file, "rb") as file:
                    st.download_button(
                        label="Download Scraped File",
                        data=file,
                        file_name="scraped_data.csv",
                        mime="text/csv",
                        key="down-button"
                        )
                uploaded_file = downloaded_file
    # Main Application
    if uploaded_file:
        save_uploaded_file(uploaded_file)
        st.success(f"File saved in memory: {uploaded_file.name}")
        st.write(f"Uploaded at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        processed_data = process_financial_data(uploaded_file)
        if processed_data is not None:
            # Split Data into Non-SME and SME
            non_sme = processed_data[processed_data['Is SME'] == 0].sort_values(by='Gain%', ascending=False)
            sme = processed_data[processed_data['Is SME'] == 1].sort_values(by='Gain%', ascending=False)
            non_sme_screened =  processed_data[(processed_data['Is SME'] == 0) & (processed_data['Sales']>50) & (processed_data['Operating profit']>10)].sort_values(by='Gain%', ascending=False)
            sme_screened =  processed_data[(processed_data['Is SME'] == 1) & (processed_data['Sales']>5) & (processed_data['Operating profit']>1)].sort_values(by='Gain%', ascending=False)
            # Tab Layout
            tab1, tab2, tab3, tab4 = st.tabs(["Non-SME Companies", "SME Companies","Non-SME Screened Companies","SME Screened Companies"])

            with tab1:
                st.subheader("Non-SME Companies")
                grid_options = configure_aggrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']])
                AgGrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], gridOptions=grid_options, fit_columns_on_grid_load=True, height=30, key="non_sme_table")

                #st.dataframe(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], use_container_width=True, hide_index=True)

            with tab2:
                st.subheader("SME Companies")
                grid_options = configure_aggrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']])
                AgGrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], gridOptions=grid_options, fit_columns_on_grid_load=True, height=30, key="sme_table")
                #st.dataframe(sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']],use_container_width=True, hide_index=True)
        
            with tab3:
                st.subheader("Non-SME Screened Companies")
                grid_options = configure_aggrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']])
                AgGrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], gridOptions=grid_options, fit_columns_on_grid_load=True, height=30, key="non_sme_s_table")
                #st.dataframe(non_sme_screened[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], use_container_width=True, hide_index=True)

            with tab4:
                st.subheader("SME Screened Companies")
                grid_options = configure_aggrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']])
                AgGrid(non_sme[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], gridOptions=grid_options, fit_columns_on_grid_load=True, height=30, key="sme_s_table")
                #st.dataframe(sme_screened[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']], use_container_width=True, hide_index=True)

        

        # After processing the data, add this button for download
        if uploaded_file and processed_data is not None:
            # Prepare the data for downloading
            download_data = processed_data[['Name', 'Market Capitalisation', 'Current Price', 'Final expected price', 'Gain%', 'Value as per EV/EBITDA Method', 'Value as per Revenue Method', 'Value as per PE Multiple', 'Value as per PB Multiple', 'PB_elements_is_1']].sort_values(by='Gain%', ascending=False)

            # Convert the dataframe to CSV format
            csv_data = convert_df_to_csv(download_data)

            # Add the download button on the Streamlit app
            st.download_button(
                label="Download All Companies as CSV",
                data=csv_data,
                file_name="company_financials.csv",
                mime="text/csv",
                use_container_width=True  # Makes the button stretch to the container width
                )
            
            # Automate scraping if URL is provided
            if st.button("Scrape Data"):
                download_dir = os.getcwd()
                with st.spinner("Scraping data..."):
                    downloaded_file = download_file_from_screener_with_login(scraping_url, download_dir)
                    if downloaded_file:
                        st.success("Data scraped successfully.")
                        with open(downloaded_file, "rb") as file:
                            st.download_button(
                                label="Download Scraped File",
                                data=file,
                                file_name="scraped_data.csv",
                                mime="text/csv",
                                )
                        uploaded_file = downloaded_file


            # Bottom Filter Section
            st.subheader("Select and Filter Company Data")
            filter_company = st.selectbox("Select a Company for Summary", processed_data['Name'].unique())

            if filter_company:
                filtered_company = processed_data[processed_data['Name'] == filter_company].iloc[0]
                display_financial_health_summary(filtered_company)

            else:
                st.info("Please upload a CSV file to proceed.")
    
    # Download last uploaded file
    if st.session_state['uploaded_file']:
        st.download_button(
            label="Download Last Uploaded File",
            data=st.session_state['uploaded_file'].getvalue(),
            file_name=st.session_state['uploaded_file'].name,
            mime="text/csv"
        )

# Tab 2: Portfolio Analysis
with tabs[1]:
    st.header("Portfolio Analysis")

    # Upload Portfolio and All Stocks Files
    portfolio_file = st.file_uploader("Upload Portfolio CSV", type="csv")
    all_stocks_file = st.file_uploader("Upload All Stocks CSV", type="csv")

    if portfolio_file and all_stocks_file:
        # Load data
        portfolio_df = pd.read_csv(portfolio_file)
        all_stocks_df = pd.read_csv(all_stocks_file)

        # Process data
        def process_portfolio_data(portfolio_df, all_stocks_df):
            merged_df = portfolio_df.merge(all_stocks_df, left_on="Instrument", right_on="NSE Code", how="left", suffixes=("_portfolio","_stocks"))
            merged_df['P&L/%'] = ((merged_df['LTP'] * merged_df['Qty.']) - 
                                  (merged_df['Avg. cost'] * merged_df['Qty.'])) / \
                                 (merged_df['Avg. cost'] * merged_df['Qty.']) * 100
            merged_df['Max Value'] = merged_df[['Avg. cost', 'LTP']].max(axis=1)
            merged_df['EBITDA'] = merged_df['Operating profit']
            merged_df['Market Capitalisation'] = merged_df['Market Capitalization']
            merged_df['Enterprise Value'] = merged_df.apply(calculate_ev, axis=1)
            merged_df['EV/EBITDA'] = merged_df.apply(calculate_ev_ebitda, axis=1)
            merged_df = calculate_ev_ebitda_share_price(merged_df)
            merged_df = calculate_revenue_method_share_price(merged_df)
            merged_df = calculate_pe_method_share_price(merged_df)
            merged_df = calculate_pb_method_share_price(merged_df)
            merged_df = calculate_gain_percentage(merged_df)
            merged_df['HOLD/SELL'] = merged_df.apply(
                lambda row: 'HOLD' if row['Final expected price'] > row['Max Value'] else 'SELL', axis=1
            )
            return merged_df

        processed_portfolio = process_portfolio_data(portfolio_df, all_stocks_df)

        # Display processed portfolio
        st.subheader("Processed Portfolio Data")
        selected_columns = ['Instrument','Qty.', 'Avg. cost', 'LTP', 'P&L/%', 'Max Value', 'Final expected price','HOLD/SELL']
        st.dataframe(processed_portfolio[selected_columns])

        # Generate and display graphs
        st.subheader("Graphs")
        col1, col2 = st.columns(2)

        def generate_market_cap_chart(df):
            df['Market Cap Category'] = pd.cut(
                df['Market Capitalization'],
                bins=[0, 5000, 20000, float('inf')],
                labels=['Small-Cap', 'Mid-Cap', 'Large-Cap']
            )
            market_cap_counts = df['Market Cap Category'].value_counts().reset_index()
            market_cap_counts.columns = ['Market Cap Category', 'Count']
            fig = px.pie(
                market_cap_counts, 
                names='Market Cap Category', 
                values='Count', 
                title='Market Capitalization Distribution'
            )
            return fig

        def generate_industry_chart(df):
            industry_counts = df['Industry'].value_counts().reset_index()
            industry_counts.columns = ['Industry', 'Count']
            fig = px.bar(
                industry_counts, 
                x='Industry', 
                y='Count', 
                title='Industry Distribution', 
                text='Count'
            )
            fig.update_traces(textposition='outside')
            return fig

        with col1:
            market_cap_chart = generate_market_cap_chart(processed_portfolio)
            st.plotly_chart(market_cap_chart)

        with col2:
            industry_chart = generate_industry_chart(processed_portfolio)
            st.plotly_chart(industry_chart)

        # Download processed data
        st.subheader("Download Processed Portfolio")
        csv_data = processed_portfolio.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Processed Portfolio as CSV",
            data=csv_data,
            file_name="processed_portfolio.csv",
            mime="text/csv"
        )
    else:
        st.info("Please upload both Portfolio and All Stocks CSV files.")


