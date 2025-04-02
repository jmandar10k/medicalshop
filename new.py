import streamlit as st
import mysql.connector
import datetime
import pandas as pd
import os
from dotenv import load_dotenv
import ssl

# Load environment variables
load_dotenv()

def get_db_connection():
    # Create SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca="ca.pem",  # You'll need to download this from Aiven
        ssl_verify_cert=True,
        ssl_disabled=False
    )

# Set page configuration
st.set_page_config(
    page_title="Medical Shop Management",
    page_icon="🏥",
    layout="wide"
)

# Initialize session state
if 'selected_medicines' not in st.session_state:
    st.session_state.selected_medicines = []
if 'strip_quantities' not in st.session_state:
    st.session_state.strip_quantities = {}

# Sidebar Navigation
st.sidebar.title("🏥 Medical Shop")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Add Patient", "Search Patient"]
)

# Dashboard Page
if page == "Dashboard":
    st.title("📊 Dashboard")
    
    # Get statistics
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total Patients
    cursor.execute("SELECT COUNT(*) FROM patients")
    total_patients = cursor.fetchone()[0]
    
    # Total Medicines
    cursor.execute("SELECT COUNT(*) FROM medicines")
    total_medicines = cursor.fetchone()[0]
    
    # Today's Reminders
    today = datetime.date.today()
    cursor.execute("""
        SELECT COUNT(DISTINCT p.id)
        FROM patients p
        WHERE p.next_reminder_date = %s
    """, (today,))
    today_reminders = cursor.fetchone()[0]
    
    # Upcoming Reminders (next 7 days)
    next_week = today + datetime.timedelta(days=7)
    cursor.execute("""
        SELECT COUNT(DISTINCT p.id)
        FROM patients p
        WHERE p.next_reminder_date BETWEEN %s AND %s
    """, (today, next_week))
    upcoming_reminders = cursor.fetchone()[0]
    
    conn.close()
    
    # Display Statistics in Columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Patients",
            total_patients,
            "👥"
        )
    
    with col2:
        st.metric(
            "Total Medicines",
            total_medicines,
            "💊"
        )
    
    with col3:
        st.metric(
            "Today's Reminders",
            today_reminders,
            "🔔"
        )
    
    with col4:
        st.metric(
            "Upcoming Reminders",
            upcoming_reminders,
            "📅"
        )
    
    # Today's Reminders Section
    st.subheader("📅 Today's Reminders")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, p.mobile, GROUP_CONCAT(CONCAT(pm.medicine_name, ' (', pm.strips, ' strips)') SEPARATOR ', ') AS medicines
        FROM patients p
        JOIN patient_medicines pm ON p.id = pm.patient_id
        WHERE p.next_reminder_date = %s
        GROUP BY p.id
    """, (today,))
    due_patients = cursor.fetchall()
    conn.close()
    
    if due_patients:
        # Convert to DataFrame for better display
        df_reminders = pd.DataFrame(due_patients, columns=['Patient Name', 'Mobile', 'Medicines'])
        st.dataframe(
            df_reminders,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Patient Name": st.column_config.TextColumn("Patient Name", width="medium"),
                "Mobile": st.column_config.TextColumn("Mobile", width="medium"),
                "Medicines": st.column_config.TextColumn("Medicines", width="large")
            }
        )
    else:
        st.success("No reminders for today!")

# Add Patient Page
elif page == "Add Patient":
    st.title("➕ Add New Patient")
    
    # Fetch medicines from database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM medicines")
    medicines = [med[0] for med in cursor.fetchall()]
    conn.close()
    
    # Patient Information Section
    st.subheader("Patient Information")
    name = st.text_input("Patient Name")
    mobile = st.text_input("Mobile Number")
    
    # Medicine Selection Section
    st.subheader("Select Medicines")
    selected_medicines = st.multiselect(
        "Select Medicines",
        medicines,
        key="med_select"
    )
    
    # Update selected medicines in session state
    if selected_medicines:
        st.session_state.selected_medicines = selected_medicines
    
    # Quantity Input Section (appears immediately after medicine selection)
    if st.session_state.selected_medicines:
        st.subheader("Enter Quantities")
        for med in st.session_state.selected_medicines:
            quantity = st.number_input(
                f"Number of strips for {med}",
                min_value=1,
                value=st.session_state.strip_quantities.get(med, 1),
                step=1,
                key=f"strips_{med}"
            )
            st.session_state.strip_quantities[med] = quantity
    
    # Last Purchase Date
    last_purchase = st.date_input("Last Purchase Date", datetime.date.today())
    
    # Add Patient Button (only enabled when all required fields are filled)
    if st.session_state.selected_medicines:
        submit_button = st.button("Add Patient")
    else:
        submit_button = st.button("Add Patient", disabled=True)
    
    # Handle form submission
    if submit_button:
        # Validate all required fields
        if not name or not mobile:
            st.error("⚠️ Please enter patient name and mobile number.")
        elif not st.session_state.selected_medicines:
            st.error("⚠️ Please select at least one medicine.")
        else:
            # Check if all quantities are entered
            all_quantities_entered = all(med in st.session_state.strip_quantities 
                                      for med in st.session_state.selected_medicines)
            
            if not all_quantities_entered:
                st.error("⚠️ Please enter quantities for all selected medicines.")
            else:
                next_reminder = last_purchase + datetime.timedelta(days=30)
                conn = get_db_connection()
                cursor = conn.cursor()
    
                try:
                    # Insert patient
                    cursor.execute(
                        "INSERT INTO patients (name, mobile, last_purchase_date, next_reminder_date) VALUES (%s, %s, %s, %s)",
                        (name, mobile, last_purchase, next_reminder)
                    )
                    patient_id = cursor.lastrowid
    
                    # Insert medicines with strip quantity
                    for med in st.session_state.selected_medicines:
                        cursor.execute(
                            "INSERT INTO patient_medicines (patient_id, medicine_name, strips) VALUES (%s, %s, %s)",
                            (patient_id, med, st.session_state.strip_quantities[med])
                        )
    
                    conn.commit()
                    st.success(f"✅ Patient Added! Reminder set for: {next_reminder}")
                    
                    # Clear the session state after successful submission
                    st.session_state.selected_medicines = []
                    st.session_state.strip_quantities = {}
                    
                except Exception as e:
                    st.error(f"Error occurred: {str(e)}")
                    conn.rollback()
                finally:
                    conn.close()

# Search Patient Page
elif page == "Search Patient":
    st.title("🔍 Search Patient")
    
    search_name = st.text_input("Enter Patient Name to Search")
    if search_name:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.name, p.mobile, p.last_purchase_date, p.next_reminder_date,
                   GROUP_CONCAT(CONCAT(pm.medicine_name, ' (', pm.strips, ' strips)') SEPARATOR ', ') AS medicines
            FROM patients p
            LEFT JOIN patient_medicines pm ON p.id = pm.patient_id
            WHERE p.name LIKE %s
            GROUP BY p.id
        """, (f"%{search_name}%",))
        
        search_results = cursor.fetchall()
        conn.close()
        
        if search_results:
            # Convert to DataFrame for better display
            df_patients = pd.DataFrame(
                search_results,
                columns=['ID', 'Name', 'Mobile', 'Last Purchase', 'Next Reminder', 'Medicines']
            )
            
            # Format dates
            df_patients['Last Purchase'] = pd.to_datetime(df_patients['Last Purchase']).dt.strftime('%Y-%m-%d')
            df_patients['Next Reminder'] = pd.to_datetime(df_patients['Next Reminder']).dt.strftime('%Y-%m-%d')
            
            st.dataframe(
                df_patients,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "Name": st.column_config.TextColumn("Name", width="medium"),
                    "Mobile": st.column_config.TextColumn("Mobile", width="medium"),
                    "Last Purchase": st.column_config.TextColumn("Last Purchase", width="medium"),
                    "Next Reminder": st.column_config.TextColumn("Next Reminder", width="medium"),
                    "Medicines": st.column_config.TextColumn("Medicines", width="large")
                }
            )
        else:
            st.warning("No patients found with that name.")