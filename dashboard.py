import streamlit as st
import pandas as pd

st.title("Transaction Dashboard")

# Load data
@st.cache_data
def load_data():
    df = pd.read_csv("master_transactions.csv", parse_dates=["Date"])
    df["Date"] = pd.to_datetime(df["Date"])
    return df

df = load_data()

# Sidebar - Date filter
st.sidebar.header("Filter by Date")
start_date = st.sidebar.date_input("Start date", df["Date"].min())
end_date = st.sidebar.date_input("End date", df["Date"].max())

# Sidebar - Payment method filter
st.sidebar.header("Filter by Payment Method")
payment_methods = df["payment method"].unique().tolist()
selected_methods = st.sidebar.multiselect("Select payment method(s)", payment_methods, default=payment_methods)

# Filter data by date range and payment method
filtered_df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date)) & (df["payment method"].isin(selected_methods))]

st.write(f"### Transactions from {start_date} to {end_date}")

# Pivot by tag
st.write("#### Summary by Tag")
tag_pivot = filtered_df.pivot_table(index="tag", values="Amount", aggfunc="sum").reset_index()
st.dataframe(tag_pivot, use_container_width=True)

# Pivot by category
st.write("#### Summary by Category")
category_pivot = filtered_df.pivot_table(index="category", values="Amount", aggfunc="sum").reset_index()
st.dataframe(category_pivot, use_container_width=True)

# Pivot by vendor
st.write("#### Summary by Vendor")
vendor_pivot = filtered_df.pivot_table(index="vendor", values="Amount", aggfunc="sum").reset_index()
st.dataframe(vendor_pivot, use_container_width=True)
