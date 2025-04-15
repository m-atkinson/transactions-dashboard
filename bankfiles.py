import pandas as pd
import os
import glob

##############################################################################
# 1. A helper function to assign vendor/category/tag from the description
##############################################################################
def update_master_file(new_df, master_filename="master_transactions.csv"):
    if os.path.exists(master_filename):
        master_df = pd.read_csv(master_filename)
        master_df = pd.concat([master_df, new_df], ignore_index=True)
    else:
        master_df = new_df

    master_df.to_csv(master_filename, index=False)
    print(f"Master CSV file '{master_filename}' updated successfully.\n")


##############################################################################

vendor_rules_df = None

def load_vendor_rules(csv_path='vendor_rules.csv'):
    """
    Load vendor categorization rules from a CSV file.
    The CSV should have columns: keyword, vendor, category, tag
    """
    global vendor_rules_df
    vendor_rules_df = pd.read_csv(csv_path)
    # Convert keywords to lowercase for case-insensitive matching
    vendor_rules_df['keyword'] = vendor_rules_df['keyword'].str.lower()
    return vendor_rules_df


def determine_vendor_cat_tag(desc: str):
    """
    Looks for specific keywords in the description string (case-insensitive).
    Returns a tuple (vendor, category, tag).
    If no match, returns ("", "", "").
    """
    global vendor_rules_df

    # Load rules if not loaded yet
    if vendor_rules_df is None:
        try:
            load_vendor_rules()
        except FileNotFoundError:
            print("Warning: vendor_rules.csv not found. Using default empty rules.")
            vendor_rules_df = pd.DataFrame(columns=['keyword', 'vendor', 'category', 'tag'])

    d = desc.lower()

    # Check each rule in the DataFrame
    for _, rule in vendor_rules_df.iterrows():
        keywords = rule['keyword'].split('&')
        # Check if ALL keywords in the rule match (if multiple keywords separated by &)
        if all(kw.strip() in d for kw in keywords):
            return (rule['vendor'], rule['category'], rule['tag'])

    # No match found
    return ("", "", "")

##############################################################################
def determine_payment_method(file_path, df_content):
    """
    Determines the payment method based on file name and content.
    
    Args:
        file_path: The path to the file being processed
        df_content: The DataFrame containing the transaction data
        
    Returns:
        A string with the payment method
    """
    payment_method = ""
    
    # Check if filename contains "chase"
    if "chase" in os.path.basename(file_path).lower():
        payment_method = "chase"
    
    # Check if file content contains "Platinum Card" in any cell
    platinum_found = False
    
    # First check in the DataFrame we already loaded
    for col in df_content.columns:
        col_content = df_content[col].astype(str)
        if any("Platinum Card" in val for val in col_content):
            platinum_found = True
            break
    
    # If we didn't find it in the structured data, we should check the entire file content
    if not platinum_found:
        try:
            # For Excel files
            if file_path.lower().endswith(('.xlsx', '.xls')):
                # Try to read all sheets
                excel_file = pd.ExcelFile(file_path)
                for sheet_name in excel_file.sheet_names:
                    # Read with no specific header row to get all content
                    sheet_df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                    # Check all cells
                    for col in sheet_df.columns:
                        if any("Platinum Card" in str(val) for val in sheet_df[col] if pd.notna(val)):
                            platinum_found = True
                            break
                    if platinum_found:
                        break
            # For CSV files
            elif file_path.lower().endswith('.csv'):
                # Try reading the file as text
                with open(file_path, 'r', errors='ignore') as file:
                    file_content = file.read()
                    if "Platinum Card" in file_content:
                        platinum_found = True
        except Exception as e:
            print(f"Warning: Could not thoroughly check file for 'Platinum Card': {e}")
    
    # Set payment method to "Platinum Card" if found
    if platinum_found:
        payment_method = "amex"
            
    return payment_method

##############################################################################
def process_excel_file(excel_file):
    """
    Reads and processes the Excel file just like your original code.
    """
    print(f"\nProcessing Excel file: {excel_file}")

    # (A) Read raw so we can grab the original B2 (row=1, col=1 in 0-based is .iloc[1,1])
    try:
        raw_df = pd.read_excel(excel_file, header=None) # No header; read everything "as is"
        cell_b2_value = str(raw_df.iloc[0, 1]) # Row=0, Col=1 in 0-based indexing
        # We'll take the last 28 characters (the "28 from the right"):
        if len(cell_b2_value) >= 28:
            statement_string = cell_b2_value[-28:] # Take last 28 chars
        else:
            # If cell value is shorter than 28 chars, use the whole string or filename
            statement_string = cell_b2_value or os.path.splitext(os.path.basename(excel_file))[0]
    except Exception as e:
        print(f"Warning: Could not read B2 cell for statement string: {e}")
        # Use the file name as fallback for statement_string (without extension)
        statement_string = os.path.splitext(os.path.basename(excel_file))[0]

    # (B) Now read again using the row that truly contains the headers:
    try:
        df = pd.read_excel(excel_file, header=6)

        # Check if required columns exist
        needed_cols = ["Date", "Amount", "Description", "Appears On Your Statement As"]
        missing_cols = [col for col in needed_cols if col not in df.columns]

        if missing_cols:
            print(f"Warning: Missing columns: {missing_cols}")
            print("Available columns:", df.columns.tolist())

            # Try alternate column names or prompting user
            if "Description" not in df.columns and "DESCRIPTION" in df.columns:
                df.rename(columns={"DESCRIPTION": "Description"}, inplace=True)

            # Map the actual columns to needed columns
            column_mapping = {}
            for col in missing_cols:
                print(f"\nCouldn't find column '{col}'. Available columns:")
                for i, available_col in enumerate(df.columns):
                    print(f"{i+1}) {available_col}")
                choice = input(f"Which column should be used for '{col}'? (Enter number or 0 to skip): ")
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(df.columns):
                        column_mapping[df.columns[idx]] = col
                except ValueError:
                    pass # Skip if invalid input

            # Apply the mapping
            if column_mapping:
                df.rename(columns=column_mapping, inplace=True)

        # Check again if we have the needed columns
        missing_cols = [col for col in needed_cols if col not in df.columns]
        if missing_cols:
            print(f"Still missing required columns: {missing_cols}")
            # Create empty columns for missing ones
            for col in missing_cols:
                df[col] = ""

        # We only need these columns:
        new_df = df[needed_cols].copy()
        
        # Standardize date format - convert to datetime
        try:
            new_df["Date"] = pd.to_datetime(new_df["Date"], errors='coerce')
            if new_df["Date"].isna().any():
                print(f"Warning: Some dates could not be parsed. {new_df['Date'].isna().sum()} rows affected.")
        except Exception as e:
            print(f"Warning: Error converting dates to datetime: {e}")
            
        # Create a date range statement string
        try:
            # Get min and max dates for statement string
            min_date = new_df["Date"].min()
            max_date = new_df["Date"].max()
            
            # Format for statement string - "MM/DD/YY to MM/DD/YY"
            statement_string = f"{max_date.strftime('%m/%d/%y')} to {min_date.strftime('%m/%d/%y')}"
        except Exception as e:
            print(f"Warning: Could not create date-based statement string: {e}")
            # Keep the original statement string as fallback
            
        # Format the date column consistently as MM/DD/YY after creating the statement string    
        try:
            new_df["Date"] = new_df["Date"].dt.strftime('%m/%d/%y')
        except Exception as e:
            print(f"Warning: Error standardizing date format: {e}")

        # Combine "Description" and "Appears On Your Statement As" into a single "description"
        new_df["description"] = (
            new_df["Description"].astype(str) + ", "
            + new_df["Appears On Your Statement As"].astype(str)
        )

        # Drop the old columns
        new_df.drop(["Description", "Appears On Your Statement As"], axis=1, inplace=True)

        # Create the 'statement' column using statement_string
        new_df["statement"] = statement_string

        # (C) Now add the three new columns: vendor, category, tag
        # using our helper function that checks keywords in description.
        new_df[["vendor","category","tag"]] = new_df["description"].apply(
            lambda x: pd.Series(determine_vendor_cat_tag(x))
        )
        
        # Determine payment method based on file name and content
        payment_method = determine_payment_method(excel_file, df)
        new_df["payment method"] = payment_method

        # Check if we need to flip signs (more negative numbers than positive)
        neg_count = (new_df["Amount"] < 0).sum()
        pos_count = (new_df["Amount"] > 0).sum()

        if neg_count > pos_count:
            print("\nDetected more negative amounts than positive. Would you like to flip all signs?")
            flip_choice = input("Flip signs? (Y/N): ").strip().lower()
            if flip_choice == 'y':
                new_df["Amount"] = -new_df["Amount"]
                print("All amount signs have been flipped.")

        # Show it
        print("\nNew DataFrame from Excel (with vendor/category/tag/payment method):\n")
        print(new_df.head(20))

        # Ask for confirmation
        user_input = input("\nDoes everything look good? (Y/N): ").strip().lower()
        if user_input == "y":
            update_master_file(new_df)
        else:
            print("\nNo changes were made to the master file.\n")

    except Exception as e:
        print(f"Error processing Excel file: {e}")

##############################################################################
def process_csv_file(csv_file):
    """
    Reads and processes the CSV file in the same style as the Excel flow.
    """
    print(f"\nProcessing CSV file: {csv_file}")

    # (A) We can construct the statement string from the filename
    base_name = os.path.basename(csv_file)
    # Remove extension
    statement_string = os.path.splitext(base_name)[0]
    # If it's longer than 28 characters, use the last 28 as before
    if len(statement_string) > 28:
        statement_string = statement_string[-28:]

    # (B) Read the CSV with error handling
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        print("Trying with different encoding...")
        try:
            df = pd.read_csv(csv_file, encoding='latin1')
        except Exception as e2:
            print(f"Still failed: {e2}")
            return

    # Get available columns
    print("Available columns:", df.columns.tolist())
    
    # Check if this is a VACU file based on column structure
    vacu_columns = ["Account Number", "Post Date", "Check", "Description", 
                    "Debit", "Credit", "Status", "Balance"]
    is_vacu_file = all(col in df.columns for col in vacu_columns)
    
    # Define the columns we need
    needed_columns = ["Date", "Description"]
    # Check if we have an Amount column or Debit/Credit pair
    has_amount = "Amount" in df.columns
    has_debit_credit = "Debit" in df.columns and "Credit" in df.columns
    
    # Add Amount to needed columns if we have it
    if has_amount:
        needed_columns.append("Amount")
    
    optional_columns = ["Category", "Type"]

    # Check for column presence and create mapping for renaming
    column_mapping = {}
    missing_cols = []

    for col in needed_columns:
        if col in df.columns:
            continue # Already present

        # Check common alternative names
        alternatives = {
            "Date": ["Post Date", "Transaction Date", "TRANSACTION DATE", "DATE"],
            "Amount": ["AMOUNT", "TRANSACTION AMOUNT", "Transaction Amount"],
            "Description": ["DESCRIPTION", "Transaction Description", "Details", "DETAILS"],
            "Debit": ["DEBIT", "Debit Amount", "DR"],
            "Credit": ["CREDIT", "Credit Amount", "CR"]
        }

        found = False
        for alt in alternatives.get(col, []):
            if alt in df.columns:
                column_mapping[alt] = col
                found = True
                break

        if not found:
            # Ask user for mapping
            print(f"\nCouldn't find column '{col}'. Available columns:")
            for i, available_col in enumerate(df.columns):
                print(f"{i+1}) {available_col}")
            choice = input(f"Which column should be used for '{col}'? (Enter number or 0 to skip): ")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(df.columns):
                    column_mapping[df.columns[idx]] = col
                else:
                    missing_cols.append(col)
            except ValueError:
                missing_cols.append(col)

    # Apply column mapping
    if column_mapping:
        df.rename(columns=column_mapping, inplace=True)

    # Create empty columns for missing ones
    for col in missing_cols:
        df[col] = ""
    
    # Handle Debit/Credit columns if Amount doesn't exist
    if not has_amount and not "Amount" in df.columns:
        # Check if we have Debit and Credit columns now (after mapping)
        if "Debit" in df.columns and "Credit" in df.columns:
            print("Converting Debit/Credit columns to a single Amount column...")
            
            # Fill NaN values with empty string or 0
            df["Debit"] = df["Debit"].fillna(0)
            df["Credit"] = df["Credit"].fillna(0)
            
            # Convert to numeric, coercing errors to NaN then to 0
            df["Debit"] = pd.to_numeric(df["Debit"], errors='coerce').fillna(0)
            df["Credit"] = pd.to_numeric(df["Credit"], errors='coerce').fillna(0)
            
            # Create Amount column: Debit is positive, Credit is negative
            df["Amount"] = df["Debit"] - df["Credit"]
            
            print("Created Amount column from Debit and Credit.")
        else:
            print("Warning: Could not find 'Amount' column or 'Debit'/'Credit' columns.")
            df["Amount"] = 0  # Create a default Amount column

    # Find optional columns or use empty values
    category_col = next((c for c in df.columns if c in ["Category", "CATEGORY"]), None)
    type_col = next((c for c in df.columns if c in ["Type", "TYPE", "Transaction Type"]), None)

    # Prepare description column by combining available info
    description_parts = [df["Description"].astype(str)]

    if category_col:
        df[category_col] = df[category_col].fillna("")
        description_parts.append(df[category_col].astype(str))

    if type_col:
        df[type_col] = df[type_col].fillna("")
        description_parts.append(df[type_col].astype(str))

    # Combine columns into "description"
    # First create an empty description column
    df["description"] = ""
    # Then combine all parts with proper concatenation for pandas Series
    for i, part in enumerate(description_parts):
        if i > 0: # Add comma separator except for first part
            df["description"] = df["description"] + ", " + part.str.strip()
        else:
            df["description"] = part.str.strip()

    # Standardize date format for all transactions - strip time component
    # Convert to datetime first (if not already)
    df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
    
    # Handle any date conversion errors
    if df["Date"].isna().any():
        print(f"Warning: Some dates could not be parsed. {df['Date'].isna().sum()} rows affected.")
    
    # Build our final DataFrame
    new_df = df[["Date", "Amount", "description"]].copy()
    
    # Create a date range statement string
    try:
        # Get min and max dates for statement string
        date_objects = pd.to_datetime(new_df["Date"])
        min_date = date_objects.min()
        max_date = date_objects.max()
        
        # Format for statement string - "MM/DD/YY to MM/DD/YY"
        statement_string = f"{max_date.strftime('%m/%d/%y')} to {min_date.strftime('%m/%d/%y')}"
    except Exception as e:
        print(f"Warning: Could not create date-based statement string: {e}")
        # Keep the original statement string as fallback
    
    # Format the date column consistently as MM/DD/YY after creating the statement string
    try:
        # Remove time component and standardize format
        new_df["Date"] = new_df["Date"].dt.strftime('%m/%d/%y')
    except Exception as e:
        print(f"Warning: Error standardizing date format: {e}")
    
    new_df["statement"] = statement_string

    # (C) Now add vendor/category/tag by the same function:
    new_df[["vendor","category","tag"]] = new_df["description"].apply(
        lambda x: pd.Series(determine_vendor_cat_tag(x))
    )
    
    # Determine payment method based on file name and content
    payment_method = determine_payment_method(csv_file, df)
    
    # Override payment_method to "vacu" if this is a VACU file
    if is_vacu_file:
        payment_method = "vacu"
        
    new_df["payment method"] = payment_method

    # Check if we need to flip signs (more negative numbers than positive)
    neg_count = (new_df["Amount"] < 0).sum()
    pos_count = (new_df["Amount"] > 0).sum()

    if neg_count > pos_count:
        print("\nDetected more negative amounts than positive. Would you like to flip all signs?")
        flip_choice = input("Flip signs? (Y/N): ").strip().lower()
        if flip_choice == 'y':
            new_df["Amount"] = -new_df["Amount"]
            print("All amount signs have been flipped.")

    # Show it
    print("\nNew DataFrame from CSV (with vendor/category/tag/payment method):\n")
    print(new_df.head(20))

    # Ask for confirmation
    user_input = input("\nDoes everything look good? (Y/N): ").strip().lower()
    if user_input == "y":
        update_master_file(new_df)
    else:
        print("\nNo changes were made to the master file.\n")

##############################################################################
def list_files():
    """
    List all supported files (Excel and CSV) in the current directory.
    Returns a list of file paths.
    """
    excel_files = glob.glob('*.xlsx') + glob.glob('*.xls')
    csv_files = glob.glob('*.csv') + glob.glob('*.CSV')
    return excel_files + csv_files

def select_file():
    """
    Prompt user to select a file from a list of available files.
    Returns the selected file path or None if canceled.
    """
    files = list_files()

    if not files:
        print("No Excel or CSV files found in the current directory.")
        manual_path = input("Enter the full path to a file (or press Enter to cancel): ").strip()
        return manual_path if manual_path else None

    print("\nAvailable files:")
    for i, file in enumerate(files):
        print(f"{i+1}) {file}")
    print(f"{len(files)+1}) Enter a different path")
    print("0) Cancel")

    choice = input("Select a file (enter number): ").strip()
    try:
        choice_num = int(choice)
        if choice_num == 0:
            return None
        elif 1 <= choice_num <= len(files):
            return files[choice_num-1]
        elif choice_num == len(files)+1:
            manual_path = input("Enter the full path to a file: ").strip()
            return manual_path if manual_path else None
    except ValueError:
        print("Invalid choice.")
        return None

##############################################################################
def process_file(file_path):
    """
    Process a file based on its extension.
    """
    if not file_path:
        print("No file selected. Exiting.")
        return
        
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension in ['.xlsx', '.xls']:
        process_excel_file(file_path)
    elif file_extension == '.csv':
        process_csv_file(file_path)
    else:
        print(f"Unsupported file type: {file_extension}")
        print("Supported file types: .xlsx, .xls, .csv")

##############################################################################
def main():
    """
    Main function that automatically determines file type based on extension.
    """
    file_path = select_file()
    if file_path:
        process_file(file_path)

if __name__ == "__main__":
    main()