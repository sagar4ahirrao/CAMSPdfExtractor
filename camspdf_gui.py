import streamlit as st
import pandas as pd
import numpy as np
import os
import io
from camspdf import ProcessPDF, _LatestNav

class MutualFundAnalyzer:
    def __init__(self):
        # Initialize session state variables
        if 'combined_df' not in st.session_state:
            st.session_state.combined_df = None
        if 'investment_summary' not in st.session_state:
            st.session_state.investment_summary = None
        if 'selected_pans' not in st.session_state:
            st.session_state.selected_pans = []
        if 'selected_funds' not in st.session_state:
            st.session_state.selected_funds = []


        
    def validate_file(self, uploaded_file):
        """Validate uploaded PDF file"""
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
        if uploaded_file.size > MAX_FILE_SIZE:
            st.error(f"File size exceeds {MAX_FILE_SIZE / (1024 * 1024):.0f} MB limit.")
            return False
        
        if not uploaded_file.name.lower().endswith('.pdf'):
            st.error("Please upload only PDF files.")
            return False
        
        return True

    def process_pdf_files(self, uploaded_files, passwords):
        """Process multiple PDF files"""
        all_dataframes = []
        error_files = []
        
        for uploaded_file, password in zip(uploaded_files, passwords):
            if not self.validate_file(uploaded_file):
                error_files.append(uploaded_file.name)
                continue
            
            try:
                with open(uploaded_file.name, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                if not password:
                    st.warning(f"No password provided for {uploaded_file.name}")
                    error_files.append(uploaded_file.name)
                    os.remove(uploaded_file.name)
                    continue
                
                pp = ProcessPDF(uploaded_file.name, password)
                df = pp.get_pdf_data(output_format="df")
                
                df['source_file'] = uploaded_file.name
                all_dataframes.append(df)
                
                os.remove(uploaded_file.name)
            
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {str(e)}")
                error_files.append(uploaded_file.name)
                if os.path.exists(uploaded_file.name):
                    os.remove(uploaded_file.name)
        
        # Combine and store dataframes
        combined_df = pd.concat(all_dataframes) if all_dataframes else None
        st.session_state.combined_df = combined_df
        
        return combined_df, error_files

    def prepare_investment_data(self, df):
        """Prepare investment data with comprehensive calculations"""
        # Remove rows with empty or NaN fund names
        df = df[df['fund_name'].notna() & (df['fund_name'] != '')]
        
        # Get latest NAV
        lnav = _LatestNav()
        
        # Prepare data
        df['date'] = pd.to_datetime(df['date'], format='%d-%b-%Y')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['units'] = pd.to_numeric(df['units'], errors='coerce')
        df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
        
        # Group by fund and calculate investment details
        buy_df = df[df['txn'] == 'Buy']
        
        # Aggregate investment summary
        investment_summary = buy_df.groupby(['pan', 'fund_name']).agg({
            'amount': 'sum',
            'units': 'sum',
            'nav': 'mean'
        }).reset_index()
        
        # Improved NAV retrieval
        def get_current_nav(row):
            fund_name = row['fund_name']
            # Try multiple matching strategies
            matching_navs = [
                nav for nav in lnav.alldata 
                if (fund_name.lower() in nav.scheme_name.lower()) or 
                (fund_name.split('-')[0].strip().lower() in nav.scheme_name.lower())
            ]
            
            if matching_navs:
                # Sort by closest match and take the first
                return float(matching_navs[0].nav)
            
            # Fallback to last known NAV or 0
            return 0
        
        # Apply NAV retrieval
        investment_summary['current_nav'] = investment_summary.apply(get_current_nav, axis=1)
        
        # Calculate financial metrics
        investment_summary['current_value'] = investment_summary['units'] * investment_summary['current_nav']
        investment_summary['unrealized_gain'] = investment_summary['current_value'] - investment_summary['amount']
        
        # Prevent division by zero
        investment_summary['return_percentage'] = np.where(
            investment_summary['amount'] != 0,
            (investment_summary['unrealized_gain'] / investment_summary['amount']) * 100,
            0
        )
        
        # Rename columns for clarity
        investment_summary.rename(columns={
            'amount': 'amount_invested', 
            'units': 'total_units', 
            'nav': 'avg_price',
            'current_nav': 'current_price'
        }, inplace=True)
        
        # Store investment summary
        st.session_state.investment_summary = investment_summary
        
        return investment_summary

    def create_investment_filters(self, df):
        """
        Create advanced filters for investment data with dynamic checkboxes 
        and persistent session state without page reset
        """
        # Ensure session state is initialized
        if 'combined_df' not in st.session_state or st.session_state.combined_df is None:
            st.session_state.combined_df = df
        
        # Initialize or reset filter states if not set
        if 'selected_pans' not in st.session_state or not st.session_state.selected_pans:
            st.session_state.selected_pans = sorted(df['pan'].unique())
        
        if 'selected_funds' not in st.session_state or not st.session_state.selected_funds:
            st.session_state.selected_funds = sorted(df['fund_name'].unique())

        st.sidebar.header("🔍 Investment Filters")
        
        # PAN Filter with Checkboxes
        st.sidebar.subheader("PAN Selection")
        all_pans = sorted(df['pan'].unique())
        
        # Dynamically create PAN checkboxes
        for pan in all_pans:
            pan_key = f"pan_{pan}"
            
            # Use a unique key for each checkbox to prevent re-rendering
            pan_selected = st.sidebar.checkbox(
                f"PAN: {pan}", 
                value=pan in st.session_state.selected_pans,
                key=pan_key
            )
            
            # Update PAN selection in session state
            if pan_selected and pan not in st.session_state.selected_pans:
                st.session_state.selected_pans.append(pan)
            elif not pan_selected and pan in st.session_state.selected_pans:
                st.session_state.selected_pans.remove(pan)
        
        # Fund Name Filter with Checkboxes
        st.sidebar.subheader("Fund Selection")
        
        # Group similar fund names
        def simplify_fund_name(name):
            return name.split('-')[0].strip()
        
        # Create fund name mapping
        fund_name_mapping = {}
        for fund in df['fund_name']:
            simplified = simplify_fund_name(fund)
            if simplified not in fund_name_mapping:
                fund_name_mapping[simplified] = []
            fund_name_mapping[simplified].append(fund)
        
        # Sort simplified fund names
        all_simplified_funds = sorted(fund_name_mapping.keys())
        
        # Dynamically create Fund checkboxes
        for simplified_fund in all_simplified_funds:
            funds_in_group = fund_name_mapping[simplified_fund]
            fund_key = f"fund_{simplified_fund}"
            
            # Check if any fund in the group is currently selected
            group_selected = any(
                fund in st.session_state.selected_funds 
                for fund in funds_in_group
            )
            
            # Use a unique key for each checkbox to prevent re-rendering
            fund_selected = st.sidebar.checkbox(
                f"Fund: {simplified_fund}", 
                value=group_selected,
                key=fund_key
            )
            
            # Update fund selection in session state
            if fund_selected:
                # Add funds not already in selected_funds
                st.session_state.selected_funds.extend([
                    fund for fund in funds_in_group 
                    if fund not in st.session_state.selected_funds
                ])
            else:
                # Remove funds in this group from selected_funds
                st.session_state.selected_funds = [
                    fund for fund in st.session_state.selected_funds 
                    if fund not in funds_in_group
                ]
        
        # Apply Filters using session state
        filtered_df = df[
            (df['pan'].isin(st.session_state.selected_pans)) &
            (df['fund_name'].isin(st.session_state.selected_funds))
        ]
        
        return filtered_df


    def display_investment_summary(self, investment_summary):
        """Display comprehensive investment summary"""
        st.header("📊 Investment Portfolio")
        
        # Calculate total metrics
        total_invested = investment_summary['amount_invested'].sum()
        total_current_value = investment_summary['current_value'].sum()
        total_unrealized_gain = investment_summary['unrealized_gain'].sum()
        
        # Prevent division by zero
        total_return_percentage = (total_unrealized_gain / total_invested) * 100 if total_invested != 0 else 0
        
        # Display key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Invested", f"₹{total_invested:,.2f}")
        with col2:
            st.metric("Current Value", f"₹{total_current_value:,.2f}")
        with col3:
            st.metric("Unrealized Gain", f"₹{total_unrealized_gain:,.2f}")
        with col4:
            st.metric("Overall Return %", f"{total_return_percentage:.2f}%")
        
        # Prepare display columns
        display_columns = [
            'pan', 'fund_name', 'total_units', 'avg_price', 
            'amount_invested', 'current_price', 'current_value', 
            'unrealized_gain', 'return_percentage'
        ]
        
        # Display Investment Table with formatting
        formatted_summary = investment_summary[display_columns].copy()
        
        # Format numeric columns
        numeric_formats = {
            'total_units': '{:.2f}',
            'avg_price': '₹{:.2f}',
            'amount_invested': '₹{:,.2f}',
            'current_price': '₹{:.2f}',
            'current_value': '₹{:,.2f}',
            'unrealized_gain': '₹{:,.2f}',
            'return_percentage': '{:.2f}%'
        }
        
        for col, fmt in numeric_formats.items():
            formatted_summary[col] = formatted_summary[col].apply(fmt.format)
        
        st.dataframe(formatted_summary, use_container_width=True)
        
        # Export Options
        st.subheader("Export Options")
        col1, col2 = st.columns(2)
        
        with col1:
            # Investment Summary Export
            csv = investment_summary.to_csv(index=False)
            st.download_button(
                label="Export Investment Summary (CSV) 📄", 
                data=csv, 
                file_name="investment_summary.csv",
                mime="text/csv"
            )
        
        with col2:
            # Excel Export
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                investment_summary.to_excel(writer, sheet_name='Investment Summary', index=False)
                
                # If original transaction data is available, add it to the Excel
                if st.session_state.combined_df is not None:
                    st.session_state.combined_df.to_excel(writer, sheet_name='All Transactions', index=False)
            
            excel_buffer.seek(0)
            st.download_button(
                label="Export to Excel 📊", 
                data=excel_buffer, 
                file_name="mutual_fund_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    def main(self):
        """Main application flow"""
        st.set_page_config(page_title="Mutual Fund Portfolio Analyzer", page_icon="💼", layout="wide")
        st.title("🏦 Mutual Fund Portfolio Analyzer")
        
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
        if st.sidebar.button("Analyze Portfolio") and uploaded_files:
            with st.spinner("Processing PDFs..."):
                combined_df, error_files = self.process_pdf_files(uploaded_files, passwords)
            
            if combined_df is not None:
                # Display error files if any
                if error_files:
                    st.warning(f"Failed to process files: {', '.join(error_files)}")

                # Prepare investment data
                investment_summary = self.prepare_investment_data(combined_df)
                
                # Create Investment Filters
                filtered_summary = self.create_investment_filters(investment_summary)
                
                # Display Investment Summary
                self.display_investment_summary(filtered_summary)
            
            else:
                st.warning("No data could be extracted. Please check your PDFs and passwords.")
        if st.session_state.combined_df is not None:
            investment_summary = self.prepare_investment_data(st.session_state.combined_df)
            filtered_summary = self.create_investment_filters(investment_summary)
            self.display_investment_summary(filtered_summary)
# Run the application
if __name__ == "__main__":
    analyzer = MutualFundAnalyzer()
    analyzer.main()
