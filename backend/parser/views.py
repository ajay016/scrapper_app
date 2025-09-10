from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.http import JsonResponse
from rest_framework_simplejwt.tokens import RefreshToken
import json








def home(request):
    return render(request, 'parser/index.html')

# def login_view(request):
#     return render(request, 'parser/authentication.html')

# def login_view(request):
#     if request.method == 'POST':
#         email = request.POST.get('email')
#         password = request.POST.get('password')
#         redirect_uri = request.POST.get('redirect_uri')

#         user = authenticate(request, email=email, password=password)
#         if user:
#             refresh = RefreshToken.for_user(user)
#             access_token = str(refresh.access_token)

#             # Redirect back to the Electron app with token
#             if redirect_uri:
#                 return redirect(f"{redirect_uri}?token={access_token}&refresh={str(refresh)}")

#     redirect_uri = request.GET.get('redirect_uri', '')
#     return render(request, 'parser/authentication.html', {'redirect_uri': redirect_uri})


def login_view(request):
    if request.method == 'POST':
        # Correctly retrieve form data using request.POST
        email = request.POST.get('email')
        password = request.POST.get('password')
        redirect_uri = request.POST.get('redirect_uri')
        
        print(f"Email: {email}, Password: {password}, Redirect URI: {redirect_uri}")

        user = authenticate(request, email=email, password=password)

        if user:
            login(request, user)  # keeps web session active

            if redirect_uri:
                # Login from Electron app, return JWT via deep link in JSON
                refresh = RefreshToken.for_user(user)
                deep_link = f"{redirect_uri}?token={str(refresh.access_token)}&refresh={str(refresh)}"
                print('deep_link:', deep_link)
                return JsonResponse({
                    'success': True,
                    'message': 'Login successful.',
                    # 'redirect_uri': f"{redirect_uri}?token={str(refresh.access_token)}&refresh={str(refresh)}"
                    'deep_link': deep_link
                })
            else:
                # Login from website directly, return redirect URL in JSON
                if user.user_type == 3:
                    redirect_to = reverse('client_dashboard')
                elif user.user_type == 1:
                    redirect_to = reverse('vendor_dashboard')
                elif user.user_type == 2:
                    redirect_to = reverse('staff_dashboard')
                else:
                    redirect_to = reverse('home')
                
                return JsonResponse({'success': True, 'message': 'Login successful.', 'redirect_to': redirect_to})
        else:
            # Send JSON response for invalid credentials
            return JsonResponse({'success': False, 'message': 'Invalid email or password.'})

    # For GET request
    redirect_uri = request.GET.get('redirect_uri', '')
    return render(request, 'parser/authentication.html', {'redirect_uri': redirect_uri})