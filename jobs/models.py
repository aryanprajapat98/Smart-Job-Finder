from django.db import models
from django.contrib.auth.hashers import make_password, check_password
import uuid
from decimal import Decimal

class CustomUser(models.Model):
    USER_TYPE_CHOICES = [
        ("seeker", "Job Seeker"),
        ("employer", "Employer / Company"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15)
    password = models.CharField(max_length=255)  # stored as a hash, never plain text
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="seeker")
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        """Hash the password before saving — never store plain text."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Verify a plain-text password against the stored hash."""
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=255, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=150, blank=True)
    size = models.CharField(max_length=50, blank=True)  # e.g. "51-200"
    website = models.URLField(blank=True)
    logo_emoji = models.CharField(max_length=10, default="🟣")
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal(4.0))
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="companies")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    JOB_TYPES = [
        ("Full-time", "Full-time"),
        ("Part-time", "Part-time"),
        ("Remote", "Remote"),
        ("Internship", "Internship"),
    ]
    SALARY_PERIODS = [("year", "LPA / year"), ("month", "per month")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=200)
    job_type = models.CharField(max_length=20, choices=JOB_TYPES, default="Full-time")
    experience_level = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=150)
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    salary_period = models.CharField(max_length=10, choices=SALARY_PERIODS, default="year")
    description = models.TextField()
    requirements = models.TextField(blank=True)
    skills = models.CharField(max_length=400, blank=True, help_text="Comma separated")
    logo_emoji = models.CharField(max_length=10, default="🟣")
    deadline = models.DateField(null=True, blank=True)
    posted_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="posted_jobs")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} at {self.company.name}"

    @property
    def salary_range(self):
        if self.salary_min and self.salary_max:
            return f"₹{self.salary_min} - ₹{self.salary_max} LPA" if self.salary_period == "year" else f"₹{self.salary_min} - ₹{self.salary_max}"
        return "Not disclosed"

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.split(",") if s.strip()]


class Application(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("review", "In Review"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="applications")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "job")  # ek user ek job pe ek hi baar apply kar sake


class SavedJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="saved_jobs")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="saved_by")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "job")

class Resume(models.Model):
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    file = models.FileField(upload_to='resumes/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user}'s Resume"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="reset_tokens")
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def is_valid(self):
        from django.utils import timezone
        from datetime import timedelta
        return (not self.used) and (timezone.now() - self.created_at) < timedelta(hours=1)

    def __str__(self):
        return f"Reset token for {self.user.email}"


class OTP(models.Model):
    PURPOSE_CHOICES = [
        ("signup", "Signup Verification"),
        ("password_reset", "Password Reset"),
    ]
    email = models.EmailField()
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)

    def is_valid(self):
        from django.utils import timezone
        from datetime import timedelta
        return (not self.verified) and (timezone.now() - self.created_at) < timedelta(minutes=10)

    def __str__(self):
        return f"OTP {self.code} for {self.email} ({self.purpose})"