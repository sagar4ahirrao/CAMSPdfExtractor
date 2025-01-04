import streamlit as st
import pandas as pd
import io
from camspdf import ProcessPDF, _LatestNav

def process_pdf_files(uploaded_files, passwords):
    """Process multiple PDF files"""
    all_dataframes = []
    error_files = []
    
    for uploaded_file, password in zip(uploaded_files, passwords):
        try:
            # Save uploaded file temporarily
            with open(uploaded_file.name, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Process PDF
            pp = ProcessPDF(uploaded_file.name, password)
            df = pp.get_pdf_data(output_format="df")
            
            if df is not None:
                all_dataframes.append(df)
            
        except Exception as e:
            error_files.append((uploaded_file.name, str(e)))
    
    combined_df = pd.concat(all_dataframes) if all_dataframes else None
    return combined_df, error_files

def prepare_investment_data(df):
    """Prepare investment data with calculations"""
    # Get latest NAV data
    lnav = _LatestNav()
    
    # Convert basic numeric columns
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['units'] = pd.to_numeric(df['units'], errors='coerce')
    df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
    
    # Add current NAV
    df['current_nav'] = df['isin'].apply(
        lambda x: float(next((nav.nav for nav in lnav.alldata 
                            if nav.isin_growth == x or nav.isin_div_reinv == x), 0))
    )
    
    # Calculate derived values
    df['current_value'] = df['units'] * df['current_nav']
    df['unrealized_gain'] = df['current_value'] - df['amount']
    df['todays_gain'] = df['units'] * (df['current_nav'] - df['nav'])
    
    return df

def create_filters(df):
    """Create filters and return selected filter values"""
    if 'selected_pans' not in st.session_state:
        st.session_state.selected_pans = []
    if 'selected_funds' not in st.session_state:
        st.session_state.selected_funds = []
        
    st.sidebar.subheader("PAN Selection")
    for pan in sorted(df['pan'].unique()):
        if st.sidebar.checkbox(f"PAN: {pan}", key=f"pan_{pan}"):
            if pan not in st.session_state.selected_pans:
                st.session_state.selected_pans.append(pan)
        elif pan in st.session_state.selected_pans:
            st.session_state.selected_pans.remove(pan)
            
    st.sidebar.subheader("Fund Selection")
    for fund in sorted(df['fund_name'].unique()):
        if st.sidebar.checkbox(f"{fund}", key=f"fund_{fund}"):
            if fund not in st.session_state.selected_funds:
                st.session_state.selected_funds.append(fund)
        elif fund in st.session_state.selected_funds:
            st.session_state.selected_funds.remove(fund)
            
    return st.session_state.selected_pans, st.session_state.selected_funds

def display_portfolio(df):
    """Display filtered portfolio data"""
    # Apply filters
    if st.session_state.selected_pans:
        df = df[df['pan'].isin(st.session_state.selected_pans)]
    if st.session_state.selected_funds:
        df = df[df['fund_name'].isin(st.session_state.selected_funds)]
    
    # Calculate totals
    total_invested = df['amount'].sum()
    total_current = df['current_value'].sum()
    total_unrealized = df['unrealized_gain'].sum()
    total_today = df['todays_gain'].sum()
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Invested", f"₹{total_invested:,.2f}")
    col2.metric("Current Value", f"₹{total_current:,.2f}")
    col3.metric("Unrealized Gain", f"₹{total_unrealized:,.2f}")
    col4.metric("Today's Gain", f"₹{total_today:,.2f}")
    
    # Display table
    st.dataframe(df[[
        'pan', 'fund_name', 'units', 'nav', 'amount',
        'current_nav', 'todays_gain', 'unrealized_gain', 'current_value'
    ]].style.format({
        'amount': '₹{:,.2f}',
        'current_value': '₹{:,.2f}',
        'unrealized_gain': '₹{:,.2f}',
        'todays_gain': '₹{:,.2f}',
        'nav': '₹{:.4f}',
        'current_nav': '₹{:.4f}',
        'units': '{:.4f}'
    }))
    
    # Export buttons
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download Summary CSV",
            df.to_csv(index=False).encode('utf-8'),
            "portfolio_summary.csv",
            "text/csv"
        )
    
    with col2:
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button(
            "Download Summary Excel",
            buffer.getvalue(),
            "portfolio_summary.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def main():
    st.set_page_config(page_title="Portfolio Analyzer", layout="wide")
    
    if 'data_processed' not in st.session_state:
        uploaded_files = st.file_uploader("Upload CAMS PDFs", type="pdf", accept_multiple_files=True)
        
        if uploaded_files:
            passwords = [st.text_input(f"Password for {f.name}", type="password") for f in uploaded_files]
            
            if st.button("Process Files"):
                combined_df, errors = process_pdf_files(uploaded_files, passwords)
                if combined_df is not None:
                    st.session_state.data_processed = True
                    st.session_state.combined_df = prepare_investment_data(combined_df)
                    
    if 'data_processed' in st.session_state:
        _, _ = create_filters(st.session_state.combined_df)
        display_portfolio(st.session_state.combined_df)

if __name__ == "__main__":
    main()