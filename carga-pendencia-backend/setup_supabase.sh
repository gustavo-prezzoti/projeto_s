#!/bin/bash

# Setup script for Supabase

echo "Installing dependencies..."
pip install supabase

echo "Creating directories if they don't exist..."
mkdir -p scripts

echo "Making the initialization script executable..."
chmod +x scripts/supabase_init.py

echo "Running the Supabase initialization script..."
python scripts/supabase_init.py

echo "Setup complete!" 