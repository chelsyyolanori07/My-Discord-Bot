import discord
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks 
from dotenv import load_dotenv
import os
import asyncio
import random
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from discord.ext import tasks
import time
import io

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True  # To access message content
intents.voice_states = True #To track voice channel events
intents.members = True #Required to fetch user information
bot = commands.Bot(command_prefix='/', intents=intents)

# Dictionary to store user-specific timers
user_timers = {}
pomodoro_times = defaultdict(int)  # Track Pomodoro session times

# 1. Pomodoro Timer Command
@bot.tree.command(name='pomodoro', description='Start a Pomodoro timer with custom durations.')
async def pomodoro_slash(interaction: discord.Interaction, work_minutes: int = 25, break_minutes: int = 5):
    """Start a Pomodoro timer with a visual progress bar inside an embed."""
    user_id = str(interaction.user.id)  # Ensure user_id is a string

    # Validate user inputs
    if work_minutes <= 0 or break_minutes <= 0:
        await interaction.response.send_message("Please enter positive numbers for work and break minutes.")
        return

    # Initial embed setup
    embed = discord.Embed(
        title="Pomodoro Timer",
        description=f"Work for {work_minutes} minutes. Progress updates will follow.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Pomodoro Timer in progress")
    await interaction.response.defer()
    work_message = await interaction.followup.send(embed=embed, wait=True)

    work_time = work_minutes * 60
    break_time = break_minutes * 60
    bar_length = 20

    async def update_progress_embed(message, remaining_time, total_time, phase):
        minutes, seconds = divmod(remaining_time, 60)
        elapsed_time = total_time - remaining_time
        progress = elapsed_time / total_time
        filled_length = int(bar_length * progress)
        bar = "█" * filled_length + "–" * (bar_length - filled_length)
        if phase == 'work':
            embed.description = f"Work Timer: [{bar}] {minutes:02d}:{seconds:02d}\nWork for {work_minutes} minutes."
        else:
            embed.description = f"Break Timer: [{bar}] {minutes:02d}:{seconds:02d}\nTake a break for {break_minutes} minutes."
        await message.edit(embed=embed)

    async def start_timer(message, total_time, phase):
        start_time = time.monotonic()
        end_time = start_time + total_time

        while (remaining_time := int(end_time - time.monotonic())) > 0:
            await update_progress_embed(message, remaining_time, total_time, phase)
            await asyncio.sleep(0.5)

        # Explicitly update the embed for 00:00
        await update_progress_embed(message, 0, total_time, phase)

        if phase == 'work':
            # Work timer complete, send a new message for the break timer
            break_embed = discord.Embed(
                title="Break Time!",
                description=f"Get some rest for {break_minutes} minutes. A progress bar will track your break.",
                color=discord.Color.green()
            )
            break_message = await interaction.followup.send(embed=break_embed)
            await start_timer(break_message, break_time, 'break')  # Start the break timer
        else:
            # Break timer complete
            embed.title = "Pomodoro Session Complete!"
            embed.description = "You've completed a Pomodoro session! Great job buddy :)"
            embed.color = discord.Color.green()
            await message.edit(embed=embed)

            # Remove the timer for the user
            if user_id in user_timers:
                del user_timers[user_id]

            # Log the completed study time
            elapsed_minutes = work_minutes  # Only count the work time
            pomodoro_times[user_id] += elapsed_minutes

    # Cancel any existing timer for the user before starting a new one
    if user_id in user_timers and user_timers[user_id] is not None:
        user_timers[user_id].cancel()

    user_timers[user_id] = asyncio.create_task(start_timer(work_message, work_time, 'work'))

# Stop Timer Command
@bot.tree.command(name='stop_timer', description='Stop the Pomodoro timer if it is running.')
async def stop_timer(interaction: discord.Interaction):
    user_id = str(interaction.user.id)  # Ensure user_id is a string

    if user_id in user_timers and user_timers[user_id] is not None:
        user_timers[user_id].cancel()
        user_timers[user_id] = None
        embed = discord.Embed(
            title="Pomodoro Timer Stopped",
            description="The timer has been stopped successfully.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="No Timer Running",
            description="No timer is currently running.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

# 2. To-Do List Commands
# Dictionary to store tasks uniquely for each user
to_do_list = defaultdict(list)

@bot.tree.command(name='add_task', description='Add a task to your to-do list')
async def add_task_slash(interaction: discord.Interaction, task: str):
    """Adds a task to the user's personal to-do list."""
    user_id = str(interaction.user.id)  # Use the user's ID as a unique key
    tasks = task.split(',')  # Split the input string into multiple tasks by commas
    for task in tasks:
        to_do_list[user_id].append((task.strip(), False))  # Add each task to the user's list with a "done" status
    embed = discord.Embed(title="To-Do List Update", description=f"Added tasks: {', '.join(task[0] for task in to_do_list[user_id])} to your to-do list!", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='show_tasks', description='Show all tasks in your to-do list')
async def show_tasks_slash(interaction: discord.Interaction):
    """Shows all tasks in the user's personal to-do list."""
    user_id = str(interaction.user.id)
    if user_id not in to_do_list or not to_do_list[user_id]:
        embed = discord.Embed(title="To-Do List", description="Your to-do list is empty!", color=discord.Color.blue())
    else:
        # Calculate the percentage of completed tasks
        total_tasks = len(to_do_list[user_id])
        completed_tasks = sum(1 for task in to_do_list[user_id] if task[1])
        completion_percentage = (completed_tasks / total_tasks) * 100

        # Format the task list for display
        tasks_list = "\n".join([f"{i + 1}. {task[0]} {'✅' if task[1] else ''}" for i, task in enumerate(to_do_list[user_id])])
        embed = discord.Embed(title="To-Do List", description=f"Your to-do list:\n{tasks_list}\n\n**Completion: {completion_percentage:.2f}%**", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_task", description="Remove a task by its number.")
async def remove_task_slash(interaction: discord.Interaction, index: int):
    user_id = str(interaction.user.id)
    try:
        if user_id not in to_do_list or not (1 <= index <= len(to_do_list[user_id])):
            embed = discord.Embed(title="Error", description="Invalid task number! Make sure the number is within the range of your tasks.", color=discord.Color.red())
        else:
            removed_task = to_do_list[user_id].pop(index - 1)
            embed = discord.Embed(title="To-Do List Update", description=f"Removed task: '{removed_task[0]}' {'✅' if removed_task[1] else ''}", color=discord.Color.blue())
    except IndexError:
        embed = discord.Embed(title="Error", description="Invalid task number! Make sure the number is within the range of your tasks.", color=discord.Color.red())
    except ValueError:
        embed = discord.Embed(title="Error", description="Please enter a valid integer for the task index.", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='mark_task_done', description='Mark a task as done by its number.')
async def mark_task_done_slash(interaction: discord.Interaction, index: int):
    user_id = str(interaction.user.id)
    try:
        if user_id not in to_do_list or not (1 <= index <= len(to_do_list[user_id])):
            embed = discord.Embed(title="Error", description="Invalid task number! Make sure the number is within the range of your tasks.", color=discord.Color.red())
        else:
            task, _ = to_do_list[user_id][index - 1]
            to_do_list[user_id][index - 1] = (task, True)
            embed = discord.Embed(title="To-Do List Update", description=f"Marked task '{task}' as done ✅. Look at you finishing that task, good luck with your other task :)", color=discord.Color.green())
    except IndexError:
        embed = discord.Embed(title="Error", description="Invalid task number! Make sure the number is within the range of your tasks.", color=discord.Color.red())
    except ValueError:
        embed = discord.Embed(title="Error", description="Please enter a valid integer for the task index.", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

# 3. Study Tracker (Dictionary to store user study times)
study_times = defaultdict(int)  # Format: {user_id: total_minutes}
voice_channel_start_times = {}

# Weekly Reset Timer (Set the initial reset time to be in UTC)
reset_time = datetime.now(timezone.utc) + timedelta(weeks=1)

# Configuration for tracked voice channels
tracked_channels = set()  # Set of channel IDs that the bot will track

@bot.event
async def on_voice_state_update(member, before, after):
    user_id = str(member.id)
    
    if not before.channel and after.channel:  # User joins a voice channel
        if after.channel.id in tracked_channels:
            voice_channel_start_times[user_id] = datetime.now(timezone.utc)
    elif before.channel and not after.channel:  # User leaves a voice channel
        if before.channel.id in tracked_channels:
            if user_id in voice_channel_start_times:
                start_time = voice_channel_start_times.pop(user_id)
                elapsed_minutes = (datetime.now(timezone.utc) - start_time).total_seconds() // 60
                study_times[user_id] += int(elapsed_minutes)

@bot.tree.command(name='log_study', description='Check your total Pomodoro study time')
async def log_study_slash(interaction: discord.Interaction):
    """Check your total Pomodoro study time."""
    user_id = str(interaction.user.id)
    total_pomodoro_time = pomodoro_times[user_id]
    embed = discord.Embed(
        title="Pomodoro Study Time",
        description=f"{interaction.user.name}, you have studied for a total of {total_pomodoro_time} minutes using Pomodoro sessions!",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='show_leaderboard', description='Display the weekly study leaderboard')
async def show_leaderboard_slash(interaction: discord.Interaction):
    await send_leaderboard(interaction.channel, interaction=interaction)

@bot.tree.command(name='add_study_room', description='Add a study room')
@commands.has_permissions(administrator=True)
async def add_study_room(interaction: discord.Interaction, room_id: str):
    """Add a study room (admin command)."""
    try:
        room_id_int = int(room_id)  # Try converting to int for internal use
        if room_id_int in tracked_channels:
            embed = discord.Embed(
                title="Study Room Already Added",
                description=f"Study room with ID {room_id_int} is already added.",
                color=discord.Color.yellow()
            )
            await interaction.response.send_message(embed=embed)
        else:
            tracked_channels.add(room_id_int)  # Add the integer to the set
            embed = discord.Embed(
                title="Study Room Added",
                description=f"Study room with ID {room_id_int} added!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
    except ValueError:
        embed = discord.Embed(
            title="Invalid Room ID",
            description="Invalid room ID. Please provide a numeric ID.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='remove_study_room', description='Remove a study room')
@commands.has_permissions(administrator=True)
async def remove_study_room(interaction: discord.Interaction, room_id: str):
    """Remove a study room (admin command)."""
    try:
        room_id_int = int(room_id)  # Try converting to int for internal use
        if room_id_int not in tracked_channels:
            embed = discord.Embed(
                title="Study Room Not Found",
                description=f"Study room with ID {room_id_int} is not in the list.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
        else:
            tracked_channels.discard(room_id_int)
            embed = discord.Embed(
                title="Study Room Removed",
                description=f"Study room with ID {room_id_int} removed!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
    except ValueError:
        embed = discord.Embed(
            title="Invalid Room ID",
            description="Invalid room ID. Please provide a numeric ID.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

def format_time(minutes):
    """Format time from minutes to hours and minutes."""
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours > 0:
        return f"{hours} hours and {remaining_minutes} minutes"
    else:
        return f"{remaining_minutes} minutes"

async def send_leaderboard(channel, interaction=None):
    """Generate and send the leaderboard to a specified channel."""
    combined_times = defaultdict(int)
    
    # Combine Pomodoro times and voice channel study times
    for user_id, pomodoro_time in pomodoro_times.items():
        combined_times[user_id] += pomodoro_time
    for user_id, study_time in study_times.items():
        combined_times[user_id] += study_time

    sorted_users = sorted(combined_times.items(), key=lambda x: x[1], reverse=True)
    if not sorted_users:
        embed = discord.Embed(
            title="No Study Times Logged",
            description="No study times logged yet.",
            color=discord.Color.blue()
        )
        if interaction:
            await interaction.response.send_message(embed=embed)
        else:
            await channel.send(embed=embed)
        return

    leaderboard_text = "\n".join(
        [f"{i + 1}. <@{user_id}>: {format_time(minutes)}" for i, (user_id, minutes) in enumerate(sorted_users[:10])]
    )
    embed = discord.Embed(
        title="Weekly Study Leaderboard",
        description=f"Top 10 of This Week! Congratulations keep up the good work :):\n{leaderboard_text}",
        color=discord.Color.blue()
    )
    if interaction:
        await interaction.response.send_message(embed=embed)
    else:
        await channel.send(embed=embed)

@tasks.loop(hours=1)  # Check every hour
async def reset_leaderboard():
    """Reset the leaderboard weekly."""
    global reset_time, study_times, pomodoro_times
    now_utc = datetime.now(timezone.utc)
    if now_utc >= reset_time:
        for guild in bot.guilds:  # Send to all servers the bot is in
            for channel in guild.text_channels:
                if channel.id == 1021442546083319822 and channel.permissions_for(guild.me).send_messages:
                    await channel.send(embed=discord.Embed(
                        title="Weekly Leaderboard Reset",
                        description="Weekly leaderboard has been reset! Log your study times for the new week!",
                        color=discord.Color.blue()
                    ))
                    break
        study_times.clear()
        pomodoro_times.clear()
        reset_time = now_utc + timedelta(weeks=1)

@tasks.loop(hours=1)  # Check every hour
async def show_leaderboard_automatically():
    """Display the weekly study leaderboard automatically every week at midnight UTC+0."""
    global bot_start_time
    if bot_start_time and datetime.now(timezone.utc) - bot_start_time < timedelta(hours=1):
        # Skip the first run if the bot has just started
        print("Skipping first run of show_leaderboard_automatically")
        return
    
    now = datetime.now(timezone.utc)  # Ensure 'now' is defined here
    if now.weekday() == 0 and now.hour == 0:  # At midnight on Monday UTC
        print("It's Monday at midnight UTC, generating leaderboard...")  # Debug print
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.id == 1021442546083319822 and channel.permissions_for(guild.me).send_messages:
                    await send_leaderboard(channel)
                    break

# 4. Motivational Messages Command
motivational_quotes = [
    "You can do it! 💪",
    "Believe in yourself! 🌟",
    "Keep pushing forward, no matter what. 🚀",
    "Every step counts. Take it one at a time. 👣",
    "Don't forget how amazing you are! 🌈",
    "You’ve got this! 💯",
    "Success doesn’t come from what you do occasionally, it comes from what you do consistently. 🌈",
    "Stay focused, go after your dreams and keep moving toward your goals. 🚶‍♀️",
    "You are capable of more than you know. 🌟",
    "Embrace the unknown. 🌌",
    "Strength doesn’t come from what you can do; it comes from overcoming the things you once thought you couldn’t. 💪",
    "Hardships often prepare ordinary people for an extraordinary destiny. 🌄",
    "Progress, not perfection. 🏆",
    "The only limit to your success is your own imagination. 💭",
    "Believe in your infinite potential. 🌈",
    "Opportunities don’t happen, you create them. 🏞️",
    "Your only limit is your mind. 🔄",
    "Dream it. Wish it. Do it. 🌈",
    "Your time is now! ⏳",
    "Your potential is endless. 🌟",
    "Stay positive, work hard, and make it happen. 💪",
    "Challenges are what make life interesting. Overcoming them is what makes life meaningful. 💪",
    "Happiness is a choice. 🎭",
    "Good things take time, but worth waiting for. 🕰️",
    "Every day is a new beginning. Take a deep breath, smile, and start again. 🌅",
    "Success is not in what you have, but who you are. 💎",
    "You are stronger than you think. 💪",
    "Small progress is still progress. 🚶‍♂️",
    "Believe you can, and you're halfway there. 💪",
    "You are braver than you believe, stronger than you seem, and smarter than you think. 🧠",
    "Your hard work will pay off. 🌱",
    "The best time for new beginnings is now. 🌱",
    "You are more capable than you give yourself credit for. 💪",
    "Take a moment to reflect on your accomplishments. 🏅",
    "Stay patient, work hard, and make it happen. 💪",
    "You are worthy of great things. ✨",
    "The only way to do great work is to love what you do. ❤️",
    "Keep going! You're closer than you think. ⛷️",
    "A positive mindset brings positive results. 🌈",
    "Embrace the journey and trust the process. 🛤️",
    "Your journey matters, so keep moving forward. 🚶‍♂️",
    "Be proud of how far you've come. 🌟",
    "Life begins at the end of your comfort zone. 🌈",
    "Start where you are. Use what you have. Do what you can. 🏞️",
    "Don’t watch the clock; do what it does. Keep going. ⏰",
    "A journey of a thousand miles begins with a single step. 🚶‍♂️",
    "Every day is a chance to begin again. 🌄",
    "Your only limit is your mindset. 💭",
    "Your dreams are valid. 🌈",
    "Inhale confidence, exhale doubt. 🌬️",
    "The best way to predict the future is to create it. 🚀",
    "You have what it takes to succeed. 💪",
    "Believe in your dreams and never give up. 🌟",
    "Each day brings new opportunities. 🌱",
    "Strength grows in the moments when you think you can’t go on, but you keep going. 💪",
    "You are enough just as you are. 💖",
    "Great things take time. 🌈",
    "You’re capable of amazing things. 🌟",
    "It’s never too late to be what you might have been. 🌄",
    "Your story isn’t over yet. 🌌",
    "Your potential is limitless. 🌟",
    "Do something today that your future self will thank you for. ✨",
    "You are braver than you feel, stronger than you seem, and loved more than you know. 💖",
    "Everything is going to be okay.. Keep going, you got this you've always have. 🥹"
]

@bot.tree.command(name='motivate', description='Get a motivational message')
async def motivate_slash(interaction: discord.Interaction):
    quote = random.choice(motivational_quotes)
    await interaction.response.send_message(quote)

# 5. Health Reminder (Background Task)
@tasks.loop(minutes=5)  # Adjust interval as needed
async def health_reminder():
    channel = bot.get_channel(1021442546083319822)  # Replace with the channel ID where reminders should be sent (Notes: How i make this diplay on multiple channel?)
    reminders = [
        "Time to drink some water! 💧",
        "Take a deep breath and relax. 🌬️",
        "Fix your posture! Sit up straight. 🪑"
        "Stretch your arms and legs. 🧘‍♀️",
        "Remember to blink and focus on your screen time. 👀",
        "Stand up and walk around for a few minutes. 🚶‍♀️",
        "Take a short break from your work. 🌻",
        "Breathe in for 4 seconds, hold for 4 seconds, breathe out for 4 seconds. 🌬️",
        "Check your eyes! Look away from the screen and focus on something far. 🧘‍♂️",
        "Have a healthy snack! 🍎",
        "Practice mindfulness for a few minutes. 🧘",
        "Do some light stretching exercises. 🏃‍♀️",
        "Give your eyes a break from screens. 🛑",
        "Remember to drink herbal tea to relax. 🍵",
        "Check your water intake for today. 💧",
        "Do some light yoga poses. 🧘‍♀️",
        "Try deep breathing exercises. 🌬️",
        "Focus on your mental health today. 💆‍♀️",
        "Take a short walk outside. 🌳",
        "Adjust your screen brightness for better eye comfort. 📱",
        "Stay hydrated throughout the day! 💧",
        "Make time to meditate. 🧘‍♂️"
    ]
    if channel:
        await channel.send(random.choice(reminders))

# 6. Help Commands
@bot.tree.command(name='help', description='Shows available commands')
async def help_slash(interaction: discord.Interaction):
    await interaction.response.defer()  # Important to defer before sending a message
    help_message = """
    **Here are the commands you can use:**
    /pomodoro [work_minutes] [break_minutes] - Start a Pomodoro timer (default 25 work, 5 break)
    /add_task [task] - Add a task to your to-do list
    /show_tasks - Show your current to-do list
    /remove_task [task_number] - Remove a task from your to-do list by its number
    /motivate - Get a motivational message
    /health_reminder - Receive health reminders every 30 minutes (running in the background)
    /log_study - Check your total Pomodoro study time
    /show_leaderboard - Display the weekly study leaderboard
    """
    await interaction.followup.send(help_message)

@bot.event
async def on_ready():
    global bot_start_time
    bot_start_time = datetime.now(timezone.utc)

    await bot.tree.sync()
    print(f"Logged in as {bot.user} and slash commands are synced!")
    health_reminder.start()  # Start the task when the bot is ready
    reset_leaderboard.start()
    show_leaderboard_automatically.start()
    print(f'We have logged in as {bot.user}')

# Run the bot
bot.run(TOKEN)
