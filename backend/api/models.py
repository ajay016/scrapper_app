from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager, Group, Permission
from django.core.files.base import ContentFile
from django.db import models
import uuid






class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, user_id=None, user_type=3, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            username=username,
            user_id=user_id or f"user_{uuid.uuid4().hex[:8]}",
            user_type=user_type,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, user_id=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', 0)

        # Let create_user handle user_id generation
        return self.create_user(
            email=email,
            username=username,
            password=password,
            user_id=user_id,  # Can be None
            **extra_fields
        )


class User(AbstractBaseUser, PermissionsMixin):
    USER_TYPE_CHOICES = (
        (0, 'Root'),
        (1, 'Vendor'),
        (2, 'Staff'),
        (3, 'Client'),
    )

    STATUS_CHOICES = (
        (0, 'Inactive'),
        (1, 'Active'),
        (2, 'Suspended'),
    )
    
    SUBSCRIPTION_STATUS_CHOICES = (
        (0, 'Active'),
        (1, 'Cancelled'),
        (2, 'Expired'),
        (3, 'Trial'),
        (4, 'Past Due'),
    )

    user_id = models.CharField(unique=True, max_length=15, blank=True, null=True)
    username = models.CharField(unique=True, max_length=150, blank=True, null=True)
    email = models.EmailField(unique=True, max_length=100)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    address = models.CharField(max_length=250, blank=True, null=True)
    city = models.CharField(max_length=250, blank=True, null=True)
    state = models.CharField(max_length=250, blank=True, null=True)
    postal_code = models.CharField(max_length=50, blank=True, null=True)

    user_type = models.IntegerField(choices=USER_TYPE_CHOICES, default=2)
    user_status = models.IntegerField(choices=STATUS_CHOICES, default=1)
    subscription_status = models.IntegerField(choices=SUBSCRIPTION_STATUS_CHOICES, default=0)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    


    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        # Generate user_id only if it's not already set
        if not self.user_id:
            # You can customize the prefix and length as needed
            self.user_id = 'USR-' + str(uuid.uuid4())[:8].upper() # Example: USR-ABCDEF12
                
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    hire_date = models.DateField(null=True, blank=True)
    job_title = models.CharField(max_length=100, blank=True, null=True)
    skills = models.TextField(blank=True, null=True)
    profile_picture = models.URLField(blank=True, null=True)
    linkedin_profile = models.URLField(blank=True, null=True)
    github_profile = models.URLField(blank=True, null=True)
    biography = models.TextField(blank=True, null=True)
    timezone = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.user.username
    
    
class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    
class ProjectFolder(models.Model):
    """Folder under a Project. Groups keywords, jobs, and results."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="folders")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('project', 'name')

    def __str__(self):
        return f"{self.project.name} / {self.name}"
    

class Keyword(models.Model):
    """Keywords entered by the client for parsing/searching."""
    user = models.ForeignKey('User', on_delete=models.SET_NULL, related_name="keywords", blank=True, null=True)
    folder = models.ForeignKey('ProjectFolder', on_delete=models.CASCADE, related_name="keywords", blank=True, null=True)
    word = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.word


class SearchJob(models.Model):
    """Represents one batch/search session (can have multiple keywords)."""
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey('User', on_delete=models.SET_NULL, related_name="search_jobs", blank=True, null=True)
    folder = models.ForeignKey('ProjectFolder', on_delete=models.CASCADE, related_name="search_jobs", blank=True, null=True)
    name = models.CharField(max_length=255, help_text="Optional custom name for this job", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Job {self.id} - {self.name or self.user.email}"


class SearchSetting(models.Model):
    """Stores the configuration used for a SearchJob."""
    ENGINES = [
        ("google", "Google"),
        ("bing", "Bing"),
        ("yahoo", "Yahoo"),
        ("yandex", "Yandex"),
        ("baidu", "Baidu"),
    ]

    job = models.OneToOneField(SearchJob, on_delete=models.CASCADE, related_name="settings")
    engines = models.JSONField(default=list, help_text="List of search engines to query")
    results_per_keyword = models.PositiveIntegerField(default=10)
    crawl_depth = models.PositiveIntegerField(default=0, help_text="0 = homepage only")
    crawl_entire_domain = models.BooleanField(default=False)

    def __str__(self):
        return f"Settings for {self.job}"


class SearchResultLink(models.Model):
    """Search result links, tied to keywords and jobs."""
    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE, related_name="results")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    depth = models.PositiveIntegerField(default=0)
    job = models.ForeignKey(SearchJob, on_delete=models.SET_NULL, related_name="results", blank=True, null=True)
    user = models.ForeignKey('User', on_delete=models.SET_NULL, related_name='search_results', blank=True, null=True)
    folder = models.ForeignKey('ProjectFolder', on_delete=models.CASCADE, related_name="results", blank=True, null=True)
    url = models.URLField()
    title = models.CharField(max_length=500, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)  # extracted company name
    email = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True, help_text="Any additional extracted data")
    crawled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title or self.url}"


class CrawledPage(models.Model):
    """Represents each crawled page (depth > 0)."""
    result = models.ForeignKey(SearchResultLink, on_delete=models.CASCADE, related_name="crawled_pages")
    url = models.URLField()
    depth = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=500, blank=True, null=True)
    content_excerpt = models.TextField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    crawled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.url} (depth {self.depth})"
    

