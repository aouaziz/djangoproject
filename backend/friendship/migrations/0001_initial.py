# Generated by Django 5.1.4 on 2024-12-16 10:12

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FriendRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('receiver', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='received_friend_requests', to=settings.AUTH_USER_MODEL)),
                ('sender', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sent_friend_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Friend Requests',
                'unique_together': {('sender', 'receiver', 'status')},
            },
        ),
    ]
