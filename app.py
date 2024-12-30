import os
import time
import pandas as pd
import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from dotenv import load_dotenv 


# Load environment variables
load_dotenv()
USERNAME = os.getenv("SCRAPER_USERNAME", "default_username")
PASSWORD = os.getenv("SCRAPER_PASSWORD", "default_password")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "chromedriver-win64\\chromedriver.exe")

def init_driver(download_dir):
    options = Options()
    prefs = {"download.default_directory": download_dir}
    options.add_argument('--headless')  # Run in headless mode
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    service = Service(CHROMEDRIVER_PATH)
    service.command_line_args().append('--verbose')
    driver = webdriver.Chrome(service=service, options=options)
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

# Streamlit App Configuration
st.set_page_config(page_title="Financial Dashboard", layout="wide", page_icon="💹")
st.title("Financial Analysis Dashboard")

# Sidebar for Upload and Scraping
st.sidebar.header("Upload or Scrape Data")
uploaded_file = st.sidebar.file_uploader("Upload Stock Data (CSV)", type="csv")
scraping_url = st.sidebar.text_input("Enter the Screener.in URL:", "https://www.screener.in/screens/2284718/all-stocks-download/")

# Functions to calculate metrics
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
            df.loc[index, 'Price per Share (EV/EBITDA)'] = sum(equity_values_per_scene) / len(equity_values_per_scene)
        else:
            df.loc[index, 'Price per Share (EV/EBITDA)'] = None
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
                df.loc[index, 'Price per Share (Revenue Method)'] = (price_per_share_a + price_per_share_b) / 2
            else:
                df.loc[index, 'Price per Share (Revenue Method)'] = None
        except:
            df.loc[index, 'Price per Share (Revenue Method)'] = None
    return df

def calculate_pe_method_share_price(df):
    for index, row in df.iterrows():
        try:
            # Use default value 1 if any required column has a missing or null value
            ttm_pat = row['Profit after tax'] if pd.notnull(row['Profit after tax']) else 1
            pat_growth = (row['Profit growth'] / 100) if pd.notnull(row['Profit growth']) else 0
            price_to_earning = max(row['Price to Earning'], 1) if pd.notnull(row['Price to Earning']) else 1
            industry_pe = max(row['Industry PE'], 1) if pd.notnull(row['Industry PE']) else 1
            num_equity_shares = row['Number of equity shares'] if pd.notnull(row['Number of equity shares']) else 1

            # Scene A
            estimated_pat_a = ttm_pat * (1 + pat_growth)
            expected_mcap_a = estimated_pat_a * price_to_earning
            price_per_share_a = expected_mcap_a / num_equity_shares

            # Scene B
            pat_growth_b = pat_growth * 0.7
            estimated_pat_b = ttm_pat * (1 + pat_growth_b)
            expected_mcap_b = estimated_pat_b * price_to_earning
            price_per_share_b = expected_mcap_b / num_equity_shares

            # Scene C
            estimated_pat_c = ttm_pat * (1 + pat_growth)
            expected_mcap_c = estimated_pat_c * industry_pe
            price_per_share_c = expected_mcap_c / num_equity_shares

            # Scene D
            pat_growth_d = pat_growth * 0.7
            estimated_pat_d = ttm_pat * (1 + pat_growth_d)
            expected_mcap_d = estimated_pat_d * industry_pe
            price_per_share_d = expected_mcap_d / num_equity_shares

            # Weighted Final Value
            final_value_pe = (
                (price_per_share_a * 0.2) +
                (price_per_share_b * 0.2) +
                (price_per_share_c * 0.3) +
                (price_per_share_d * 0.3)
            )

            # Assign the calculated value to the DataFrame
            df.loc[index, 'Value as per Price to Earnings Multiple'] = final_value_pe

        except Exception as e:
            # Handle exceptions and set the output to None if any errors occur
            df.loc[index, 'Value as per Price to Earnings Multiple'] = None
            st.warning(f"Error processing row {index}: {e}")

    return df

def calculate_pb_method_share_price(df):
    for index, row in df.iterrows():
        try:
          price_to_book = max(row['Price to book value'], 1) if pd.notnull(row['Price to book value']) else 1
          industry_pb = max(row['Industry PBV'], 1) if pd.notnull(row['Industry PBV']) else 1
          book_value_2yr_back = max(row['Book value preceding year'], 1) if pd.notnull(row['Book value preceding year']) else 1
          book_value = max(row['Book value'], 1) if pd.notnull(row['Book value']) else 1

          # Growth in book value
          growth_in_book_value_a = ((book_value / book_value_2yr_back)**0.5 - 1) * 100
          growth_in_book_value_b = growth_in_book_value_a * 0.8
          growth_in_book_value_c = growth_in_book_value_a
          growth_in_book_value_d = growth_in_book_value_c * 0.8

          # Expected book value
          expected_book_value_a = book_value * (1 + growth_in_book_value_a / 100)
          expected_book_value_b = book_value * (1 + growth_in_book_value_b / 100)
          expected_book_value_c = book_value * (1 + growth_in_book_value_c / 100)
          expected_book_value_d = book_value * (1 + growth_in_book_value_d / 100)

          # Expected market price
          expected_market_price_a = expected_book_value_a * price_to_book
          expected_market_price_b = expected_book_value_b * price_to_book
          expected_market_price_c = expected_book_value_c * industry_pb
          expected_market_price_d = expected_book_value_d * industry_pb

          # Final expected market price
          final_expected_market_price_a = expected_market_price_a * 0.3
          final_expected_market_price_b = expected_market_price_b * 0.3
          final_expected_market_price_c = expected_market_price_c * 0.2
          final_expected_market_price_d = expected_market_price_d * 0.2

          # Average market price per share
          average_market_price_per_share = (
              final_expected_market_price_a +
              final_expected_market_price_b +
              final_expected_market_price_c +
              final_expected_market_price_d
              )

          # Assign the calculated value to the DataFrame
          df.loc[index, 'Value as per PB Multiple'] = average_market_price_per_share

        except Exception as e:
            # Handle exceptions and set the output to None if any errors occur
            df.loc[index, 'Value as per PB Multiple'] = None
            st.warning(f"Error processing row {index}: {e}")

    return df


def calculate_gain_percentage(df):
    for index, row in df.iterrows():
        try:
            gain = (((
                0.25 * row['Value as per Price to Earnings Multiple'] +
                0.25 * row['Price per Share (EV/EBITDA)'] +
                0.25 * row['Price per Share (Revenue Method)'] +
                0.25 * row['Value as per PB Multiple']

            ) - row['Current Price']) / row['Current Price'])*100

            df.loc[index, 'Gain%'] = gain

            df.loc[index, 'Final expected price'] = (
                0.25 * row['Value as per Price to Earnings Multiple'] +
                0.25 * row['Price per Share (EV/EBITDA)'] +
                0.25 * row['Price per Share (Revenue Method)'] +
                0.25 * row['Value as per PB Multiple']
            )
        except:
            df.loc[index, 'Gain%'] = None
    return df

# Process Data Function
def process_financial_data(input_file):
    try:
        data = pd.read_csv(input_file)
        data['EBITDA'] = data['Operating profit']
        data['Enterprise Value'] = data.apply(calculate_ev, axis=1)
        data['EV/EBITDA'] = data.apply(calculate_ev_ebitda, axis=1)
        data = calculate_ev_ebitda_share_price(data)
        data = calculate_revenue_method_share_price(data)
        data = calculate_pe_method_share_price(data)
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

        # Use st.columns for layout
        col1, col2 = st.columns(2)

        with col1:
            st.subheader(f"{row['Name']}")
            # st.metric(label="SME", value=summary['SME'])
            st.metric(label="SME", value=summary['SME'].iloc[0]) # Or st.metric(label="SME", value=summary['SME'][0]) or st.metric(label="SME", value=summary['SME'].to_string())
            # st.metric(label="Market Capitalisation", value=summary['Market Capitalisation'])
            st.metric(label="Market Capitalisation", value=summary['Market Capitalisation'].to_string())
            st.metric(label="Promoters Holding%", value=summary['Promoters Holding%'].iloc[0])
            st.metric(label="Change in PM", value=summary['Change in PM'].iloc[0])
            st.metric(label="Cash Conversion Cycle", value=summary['Cash Conversion Cycle'].iloc[0])
            st.metric(label="ROE%", value=summary['ROE%'].iloc[0])


        with col2:
            st.metric(label="Change in FII Hold%", value=summary['Change in FII Hold%'].iloc[0])
            st.metric(label="Change in DII Hold%", value=summary['Change in DII Hold%'].iloc[0])
            st.metric(label="Price to Book Value%", value=summary['Price to Book Value%'].iloc[0])
            st.metric(label="ROCE%", value=summary['ROCE%'].iloc[0])
            st.metric(label="QOQ Sales%", value=summary['QOQ Sales%'].iloc[0])
            st.metric(label="YOY Profit%", value=summary['YOY Profit%'].iloc[0])


        # Add spacing between companies
        st.markdown("<hr>", unsafe_allow_html=True)


# Automate scraping if URL is provided
if st.sidebar.button("Scrape Data"):
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

# # Process uploaded or scraped data
# if uploaded_file:
#     processed_data = process_financial_data(uploaded_file)
#     if processed_data is not None:
#         st.subheader("Top Companies by Gain%")
#         top_companies = processed_data.sort_values(by="Gain%", ascending=False).head(10)
#         st.dataframe(top_companies)

#         csv_data = processed_data.to_csv(index=False).encode("utf-8")
#         st.download_button(
#             label="Download Processed Data",
#             data=csv_data,
#             file_name="processed_data.csv",
#             mime="text/csv",
#         )


# Main Application
if uploaded_file:
    processed_data = process_financial_data(uploaded_file)
    if processed_data is not None:
        # Split Data into Non-SME and SME
        non_sme = processed_data[processed_data['Is SME'] == 0].sort_values(by='Gain%', ascending=False).head(10)
        sme = processed_data[processed_data['Is SME'] == 1].sort_values(by='Gain%', ascending=False).head(10)

        # Tab Layout
        tab1, tab2 = st.tabs(["Top 10 Non-SME Companies", "Top 10 SME Companies"])

        with tab1:
            st.subheader("Top 10 Non-SME Companies")
            st.dataframe(non_sme[['Name', 'Gain%', 'Current Price', 'Final expected price']])

        with tab2:
            st.subheader("Top 10 SME Companies")
            st.dataframe(sme[['Name', 'Gain%', 'Current Price', 'Final expected price']])

    # After processing the data, add this button for download
    if uploaded_file and processed_data is not None:
      # Prepare the data for downloading
      download_data = processed_data[['Name', 'Gain%', 'Current Price', 'Final expected price']].sort_values(by='Gain%', ascending=False)

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

      # Bottom Filter Section
      st.subheader("Select and Filter Company Data")
      filter_company = st.selectbox("Select a Company for Summary", processed_data['Name'].unique())

      if filter_company:
        filtered_company = processed_data[processed_data['Name'] == filter_company].iloc[0]
        display_financial_health_summary(filtered_company)

      else:
        st.info("Please upload a CSV file to proceed.")
