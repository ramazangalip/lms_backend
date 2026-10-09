from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from .models import User, EmailOTP

from datetime import timedelta

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    remember_me = serializers.BooleanField(required=False, default=False)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['email'] = user.email
        token['is_teacher'] = user.is_teacher
        token['is_student'] = user.is_student
        token['department'] = user.department  
        token['full_name'] = f"{user.first_name} {user.last_name}"
        
        return token

    def validate(self, attrs):
        # E-posta / kullanıcı adını al, kırp ve küçük harfe çevir
        raw_email = attrs.get('email') or attrs.get('username') or ''
        email_val = str(raw_email).strip().lower()
        password = attrs.get('password')

        user = None
        if email_val:
            user = User.objects.filter(email__iexact=email_val).first() or User.objects.filter(username__iexact=email_val).first()

        # Kullanıcı yoksa veya şifre yanlışsa
        if not user or not password or not user.check_password(password):
            raise serializers.ValidationError({"detail": "Email veya şifreniz yanlıştır."})

        # Kullanıcı var ve şifre doğru. Kategoriyi kontrol et:
        if user and getattr(user, 'category', None):
            cat = str(user.category).strip().lower()
            if 'd2' in cat:
                raise serializers.ValidationError({
                    "detail": "yapayzekadesteklidijitalsinif.com.tr den giriş yapmayı deneyiniz."
                })

        # E-posta eşleşmesini veritabanındaki e-posta adresiyle eşleştir
        if 'email' in attrs:
            attrs['email'] = user.email
        if 'username' in attrs:
            attrs['username'] = user.username or user.email

        try:
            data = super().validate(attrs)
        except Exception:
            raise serializers.ValidationError({"detail": "Email veya şifreniz yanlıştır."})

        remember_me = self.initial_data.get('remember_me', False)

        if remember_me:
            refresh = self.get_token(self.user)
            refresh.set_exp(lifetime=timedelta(days=30))

            access = refresh.access_token
            access.set_exp(lifetime=timedelta(days=30))

            data['refresh'] = str(refresh)
            data['access'] = str(access)
            data['remember_me'] = True

        return data

class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        try:
            refresh = self.token_class(attrs['refresh'])
            user_id = refresh.get('user_id')
            if user_id:
                user = User.objects.filter(id=user_id).first()
                if user and user.category and 'd2' in str(user.category).strip().lower():
                    raise serializers.ValidationError({
                        "detail": "yapayzekadesteklidijitalsinif.com.tr den giriş yapmayı deneyiniz."
                    })
        except Exception as e:
            if isinstance(e, serializers.ValidationError):
                raise e
        return data

class RegisterSerializer(serializers.ModelSerializer):
    code = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    department = serializers.ChoiceField(choices=User.DEPARTMENT_CHOICES, required=True)
    
    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'code', 'department']

    def validate_email(self, value):
        if not value.endswith('@bingol.edu.tr'):
            raise serializers.ValidationError("Sadece @bingol.edu.tr uzantılı adresler kayıt olabilir.")
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Bu e-posta adresi zaten kullanımda.")
        return value

    def validate(self, data):
        email = data.get('email')
        code = data.get('code')
        
        otp_record = EmailOTP.objects.filter(email=email, code=code).first()
        if not otp_record:
            raise serializers.ValidationError({"code": "Doğrulama kodu geçersiz veya hatalı."})
        
        return data

    def create(self, validated_data):
        # Kullanılan OTP kodunu temizle
        EmailOTP.objects.filter(email=validated_data['email']).delete()
        
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            department=validated_data.get('department'),
            is_student=True,
            is_teacher=False
        )
        return user

class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, 
        validators=[validate_password], 
        style={'input_type': 'password'}
    )

    def validate_email(self, value):
        # 1. Uzantı Kontrolü
        if not value.endswith('@bingol.edu.tr'):
            raise serializers.ValidationError("Sadece @bingol.edu.tr uzantılı adresler şifre sıfırlayabilir.")
        
        
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Bu e-posta adresiyle kayıtlı bir kullanıcı bulunamadı.")
        
        return value

    def validate(self, data):
        email = data.get('email')
        code = data.get('code')

        otp_record = EmailOTP.objects.filter(email=email, code=code).first()
        if not otp_record:
            raise serializers.ValidationError({"code": "Doğrulama kodu geçersiz veya hatalı."})

        
        return data

    def save(self):
        email = self.validated_data['email']
        new_password = self.validated_data['new_password']
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()

        EmailOTP.objects.filter(email=email).delete()
        
        return user