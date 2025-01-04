import streamlit as st
import pandas as pd
import os
import numpy as np
from camspdf import ProcessPDF

def validate_file(uploaded_file):
    """
    Validate uploaded PDF file
    """
    # File size validation (max 50 MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    if uploaded_file.size > MAX_FILE_SIZE:
        st.error(f"File size exceeds {MAX_FILE_SIZE / (1024 * 1024):.0f} MB limit.")
        return False
    
    # File type validation
    if not uploaded_file.name.lower().endswith('.pdf'):
        st.error("Please upload only PDF files.")
        return False
    
    return True

def process_pdf_files(uploaded_files, passwords):
    """
    Process multiple PDF files with enhanced error handling
    """
    all_dataframes = []
    error_files = []
    
    for uploaded_file, password in zip(uploaded_files, passwords):
        # Validate file
        if not validate_file(uploaded_file):
            error_files.append(uploaded_file.name)
            continue
        
        try:
            # Save the uploaded file temporarily
            with open(uploaded_file.name, "wb") as f:
                f.write(uploaded_file.getvalue())
            
            # Validate password
            if not password:
                st.warning(f"No password provided for {uploaded_file.name}")
                error_files.append(uploaded_file.name)
                os.remove(uploaded_file.name)
                continue
            
            # Process the PDF
            pp = ProcessPDF(uploaded_file.name, password)
            df = pp.get_pdf_data(output_format="df")
            
            # Add a source file column
            df['source_file'] = uploaded_file.name
            all_dataframes.append(df)
            
            # Remove the temporary file
            os.remove(uploaded_file.name)
        
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {str(e)}")
            error_files.append(uploaded_file.name)
            # Remove temporary file if it exists
            if os.path.exists(uploaded_file.name):
                os.remove(uploaded_file.name)
    
    # Combine dataframes
    combined_df = pd.concat(all_dataframes) if all_dataframes else None
    
    return combined_df, error_files

def prepare_data(combined_df):
    """
    Prepare the data for filtering and analysis
    """
    # Convert columns to appropriate types
    combined_df['date'] = pd.to_datetime(combined_df['date'], format='%d-%b-%Y')
    combined_df['amount'] = pd.to_numeric(combined_df['amount'], errors='coerce')
    combined_df['units'] = pd.to_numeric(combined_df['units'], errors='coerce')
    combined_df['nav'] = pd.to_numeric(combined_df['nav'], errors='coerce')
    
    return combined_df

def create_advanced_filters(df):
    """
    Create advanced filters with pills and checkboxes
    """
    st.sidebar.header("🔍 Advanced Filters")
    
    # Date Range Filter
    st.sidebar.subheader("Date Range")
    min_date = df['date'].min()
    max_date = df['date'].max()
    start_date = st.sidebar.date_input("Start Date", min_date)
    end_date = st.sidebar.date_input("End Date", max_date)
    
    # Transaction Type Filter with Pills
    st.sidebar.subheader("Transaction Types")
    txn_types = df['txn'].unique()
    selected_txn_types = st.sidebar.multiselect(
        "Select Transaction Types",
        options=txn_types,
        default=txn_types,
        format_func=lambda x: f"✅ {x}" if x in txn_types else x
    )
    
    # Fund Selection with Searchable Multiselect
    st.sidebar.subheader("Fund Selection")
    all_funds = df['fund_name'].unique()
    selected_funds = st.sidebar.multiselect(
        "Select Funds",
        options=all_funds,
        default=all_funds,
        format_func=lambda x: f"✅ {x}" if x in all_funds else x
    )
    
    # Folio Number Filter
    st.sidebar.subheader("Folio Numbers")
    all_folios = df['folio_num'].unique()
    selected_folios = st.sidebar.multiselect(
        "Select Folio Numbers",
        options=all_folios,
        default=all_folios,
        format_func=lambda x: f"✅ {x}" if x in all_folios else x
    )
    
    # Amount Range Slider
    st.sidebar.subheader("Transaction Amount Range")
    min_amount = float(df['amount'].min())
    max_amount = float(df['amount'].max())
    amount_range = st.sidebar.slider(
        "Select Amount Range",
        min_value=min_amount,
        max_value=max_amount,
        value=(min_amount, max_amount)
    )
    
    # Apply Filters
    filtered_df = df[
        (df['date'].dt.date >= start_date) & 
        (df['date'].dt.date <= end_date) &
        (df['txn'].isin(selected_txn_types)) &
        (df['fund_name'].isin(selected_funds)) &
        (df['folio_num'].isin(selected_folios)) &
        (df['amount'].between(amount_range[0], amount_range[1]))
    ]
    
    return filtered_df

def display_filtered_data(filtered_df):
    """
    Display filtered data with various visualizations
    """
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Data Table", "📈 Transaction Summary", "💰 Fund Performance"])
    
    with tab1:
        st.dataframe(filtered_df)
    
    with tab2:
        # Transaction Summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Transactions", len(filtered_df))
            st.metric("Buy Transactions", len(filtered_df[filtered_df['txn'] == 'Buy']))
        with col2:
            st.metric("Total Investment", f"₹{filtered_df['amount'].sum():,.2f}")
            st.metric("Sell Transactions", len(filtered_df[filtered_df['txn'] == 'Sell']))
        with col3:
            st.metric("Unique Funds", filtered_df['fund_name'].nunique())
            st.metric("Unique Folios", filtered_df['folio_num'].nunique())
    
    with tab3:
        # Fund Performance
        fund_performance = filtered_df.groupby('fund_name').agg({
            'amount': ['sum', 'mean'],
            'units': ['sum', 'mean']
        })
        st.dataframe(fund_performance)

def main():
    st.set_page_config(page_title="CAMS PDF Analyzer", page_icon="💼", layout="wide")
    st.title("🏦 CAMS Mutual Fund Data Analyzer")
    
    # File Upload Section
    st.sidebar.header("Upload PDF Files")
    uploaded_files = st.sidebar.file_uploader(
        "Choose CAMS PDF statements", 
        type="pdf", 
        accept_multiple_files=True
    )
    
    # Password Input
    passwords = []
    if uploaded_files:
        st.sidebar.subheader("Enter PDF Passwords")
        for file in uploaded_files:
            password = st.sidebar.text_input(
                f"Password for {file.name}", 
                type="password", 
                key=file.name
            )
            passwords.append(password)
    
    # Process Button
    if st.sidebar.button("Extract Data") and uploaded_files:
        with st.spinner("Processing PDFs..."):
            combined_df, error_files = process_pdf_files(uploaded_files, passwords)
        
        if combined_df is not None:
            # Display error files if any
            if error_files:
                st.warning(f"Failed to process files: {', '.join(error_files)}")

            # Prepare data
            prepared_df = prepare_data(combined_df)
            
            # Create Advanced Filters
            filtered_df = create_advanced_filters(prepared_df)
            
            # Display Filtered Data
            display_filtered_data(filtered_df)
            
            # Export Options
            st.subheader("Export Filtered Data")
            col1, col2 = st.columns(2)
            
            with col1:
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV 📄", 
                    data=csv, 
                    file_name="filtered_mutual_fund_transactions.csv",
                    mime="text/csv"
                )
            
            with col2:
                import io
                excel_buffer = io.BytesIO()
                filtered_df.to_excel(excel_buffer, index=False)
                excel_buffer.seek(0)
                st.download_button(
                    label="Download Excel 📊", 
                    data=excel_buffer, 
                    file_name="filtered_mutual_fund_transactions.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        else:
            st.warning("No data could be extracted. Please check your PDFs and passwords.")

if __name__ == "__main__":
    main()
