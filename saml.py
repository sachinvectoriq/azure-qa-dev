import os
import json
import urllib.parse
from flask import session, redirect, request
from onelogin.saml2.auth import OneLogin_Saml2_Auth
import jwt
import datetime
from jwt import ExpiredSignatureError, InvalidTokenError

JWT_SECRET_KEY = 'VectorIQ#Dev'

def init_saml_auth(req, saml_path):
    print('In init auth')
    auth = OneLogin_Saml2_Auth(req, custom_base_path=saml_path)
    return auth

def prepare_flask_request(request):
    print('In Prepare Flask')
    url_data = request.url.split('?')
    return {
        'https': 'on',
        'http_host': request.host,
        'script_name': request.path,
        'server_port': request.host.split(':')[1] if ':' in request.host else '443',
        'get_data': request.args.copy(),
        'post_data': request.form.copy(),
    }

def saml_login(saml_path):
    print('In SAML Login')
    req = prepare_flask_request(request)
    auth = init_saml_auth(req, saml_path)
    return redirect(auth.login())

def saml_callback(saml_path):
    req = prepare_flask_request(request)
    auth = init_saml_auth(req, saml_path)
    auth.process_response()
    errors = auth.get_errors()
    group_name = 'user'

    if not errors:
        # Extract SAML attributes
        attributes = auth.get_attributes()

        # Extract email address
        email_list = attributes.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress', [])
        email_address = email_list[0] if email_list else 'no-email@example.com'

        # Extract job title
        job_title_list = attributes.get('http://schemas.microsoft.com/identity/claims/jobtitle', [])
        job_title = job_title_list[0] if job_title_list else 'No Job Title'

        user_data = {
            'name': 'Test User',
            'group': group_name,
            'email': email_address,   # Added email
            'job_title': job_title    # Added job title
        }

        token = create_jwt_token(user_data)
        # Redirect to the React dashboard with the user data
        return redirect(f'http://localhost:5173/dashboard?token={token}')
    else:
        return f"Error in SAML Authentication: {errors}-{req}", 500


def create_jwt_token(user_data):
    # Define the token expiration time (e.g., 1 hour)
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    payload = {
        'user_data': user_data,
        'exp': expiration  # Token expiration time
    }
    # Create the token
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
    return token

def get_data_from_token(token):
    try:
        # Decode the token (this will verify the signature and expiration)
        decoded_data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        # Extract user data from the decoded token
        user_data = decoded_data.get('user_data')
        return user_data

    except ExpiredSignatureError:
        return 'Error: Token has expired'

    except InvalidTokenError:
        return 'Error: Invalid token'
