import discord
from datetime import datetime, timedelta
from discord.ext import commands, tasks 
from dotenv import load_dotenv
import os
import asyncio
import random
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from discord.ext import tasks

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

# 1. Pomodoro Timer Command
@bot.tree.command(name='pomodoro', description='Start a Pomodoro timer with custom durations.')
async def pomodoro_slash(interaction: discord.Interaction, work_minutes: int = 25, break_minutes: int = 5):
    """
    Start a Pomodoro timer with a visual progress bar inside an embed.
    """
    user_id = interaction.user.id

    # Validate user inputs
    if work_minutes <= 0 or break_minutes <= 0:
        await interaction.response.send_message("Please enter positive numbers for work and break minutes.")
        return

    # Notify the user that the timer has started
    embed = discord.Embed(
        title="Pomodoro Timer",
        description=f"Work for {work_minutes} minutes. Progress updates will follow.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Pomodoro Timer in progress")

    # Ensure Interaction is Deferred
    await interaction.response.defer()

    message = await interaction.followup.send(embed=embed, wait=True)  # Send the initial embed message and store the response

    total_time = work_minutes * 60  # Total time in seconds
    bar_length = 20  # Length of the progress bar

    async def update_progress_embed(remaining_time):
        minutes, seconds = divmod(remaining_time, 60)
        elapsed_time = (work_minutes * 60) - remaining_time
        progress = elapsed_time / (work_minutes * 60)
        filled_length = int(bar_length * progress)
        bar = "█" * filled_length + "–" * (bar_length - filled_length)

        embed.description = f"Timer: [{bar}] {minutes:02d}:{seconds:02d}\nWork for {work_minutes} minutes."
        await message.edit(embed=embed)

    async def start_pomodoro_timer():
        nonlocal total_time

        while total_time > 0:
            await update_progress_embed(total_time)
            await asyncio.sleep(1)
            total_time -= 1

        # Timer complete
        embed.title = "Pomodoro Timer Complete!"
        embed.description = "Time's up! Take a break!"
        embed.color = discord.Color.green()
        await message.edit(embed=embed)  # Update embed to show completion

        # Remove the timer for the user once it completes
        if user_id in user_timers:
            del user_timers[user_id]

    # Cancel any existing timer for the user before starting a new one
    if user_id in user_timers and user_timers[user_id] is not None:
        user_timers[user_id].cancel()

    user_timers[user_id] = asyncio.create_task(start_pomodoro_timer())

# Stop Timer Command
@bot.tree.command(name='stop_timer', description='Stop the Pomodoro timer if it is running.')
async def stop_timer(interaction: discord.Interaction):
    user_id = interaction.user.id

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
        await interaction.response.send_message("No timer is currently running.")

# 2. To-Do List Commands
# Dictionary to store tasks uniquely for each user
to_do_list = {}

@bot.tree.command(name='add_task', description='Add a task to your to-do list')
async def add_task_slash(interaction: discord.Interaction, task: str):
    """Adds a task to the user's personal to-do list."""
    user_id = str(interaction.user.id)  # Use the user's ID as a unique key
    if user_id not in to_do_list:
        to_do_list[user_id] = []  # Initialize an empty list for the user if not present
    to_do_list[user_id].append(task)  # Add the task to the user's list
    await interaction.response.send_message(f"Added task: '{task}' to your to-do list!")

@bot.tree.command(name='show_tasks', description='Show all tasks in your to-do list')
async def show_tasks_slash(interaction: discord.Interaction):
    """Shows all tasks in the user's personal to-do list."""
    user_id = str(interaction.user.id)
    if user_id not in to_do_list or not to_do_list[user_id]:
        await interaction.response.send_message("Your to-do list is empty!")
    else:
        # Format the task list for display
        tasks_list = "\n".join([f"{i + 1}. {task}" for i, task in enumerate(to_do_list[user_id])])
        await interaction.response.send_message(f"Your to-do list:\n{tasks_list}")

@bot.tree.command(name="remove_task", description="Remove a task by its number.")
async def remove_task_slash(interaction: discord.Interaction, index: int):
    user_id = str(interaction.user.id)
    try:
        if user_id not in to_do_list or not (1 <= index <= len(to_do_list[user_id])):
            await interaction.response.send_message("Invalid task number! Make sure the number is within the range of your tasks.")
            return # Important to return here to avoid further execution
        removed_task = to_do_list[user_id].pop(index - 1)
        await interaction.response.send_message(f"Removed task: '{removed_task}'")
    except IndexError: # Handle index errors specifically
        await interaction.response.send_message("Invalid task number! Make sure the number is within the range of your tasks.")
    except ValueError: # Handle if the user inputs something that is not an integer
        await interaction.response.send_message("Please enter a valid integer for the task index.")

# 3. Study Tracker (Dictionary to store user study times)
study_times = defaultdict(list) #Format: {user_id: total_minutes}
voice_channel_start_times = {}

# Weekly Reset Timer
reset_time = datetime.now() + timedelta(weeks=1)

@bot.event
async def on_voice_state_update(member, before, after):
    user_id = str(member.id)
    
    if not before.channel and after.channel:  # User joins a voice channel
        voice_channel_start_times[user_id] = datetime.now()
    elif before.channel and not after.channel:  # User leaves a voice channel
        if user_id in voice_channel_start_times:
            start_time = voice_channel_start_times.pop(user_id)
            elapsed_minutes = (datetime.now() - start_time).total_seconds() // 60
            study_times[user_id] += int(elapsed_minutes)
            await member.send(f"You've logged {int(elapsed_minutes)} minutes of study time!")

@bot.tree.command(name='log_study', description='Manually log your study time')
async def log_study_slash(interaction: discord.Interaction, minutes: int):
    """Manually log study time in minutes."""
    if minutes <= 0:
        await interaction.response.send_message("Please enter a positive number of minutes.")
        return
    user_id = str(interaction.user.id)
    study_times[user_id] += minutes
    await interaction.response.send_message(f"{interaction.user.name}, you've manually logged {minutes} minutes of study time!")

@bot.tree.command(name='show_leaderboard', description='Display the weekly study leaderboard')
async def show_leaderboard_slash(interaction: discord.Interaction):
    """Generate and display the weekly study leaderboard"""
    await interaction.response.defer() #Important to defer if it will take time
    if not study_times:
        await interaction.followup.send('No study times logged yet')
        return
    # Sort users by study time
    sorted_users = sorted(study_times.items(), key=lambda x: x[1], reverse=True)
    
    # Create leaderboard image
    image_width, image_height = 600, 400
    background_color = (255, 255, 255) #white
    text_color = (0, 0, 0) #black

    image = Image.new('RGB', (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('arial.ttf', 20) #replace with another font if arial is unavailable

    # Title
    title = 'Weekly Study Leaderboard'
    draw.text((image_width // 4, 10), title, fill=text_color, font=font)

    # Add users to the leaderboard
    y_offset = 50
    for i, (user_id, minutes) in enumerate(sorted_users[:10]):  # Top 10 users
        user = await bot.fetch_user(int(user_id))
        draw.text(
            (50, y_offset),
            f"{i + 1}. {user.name}: {minutes} minutes",
            fill=text_color,
            font=font,
        )
        y_offset += 30

    # Save and send the image
    image.save("leaderboard.png")
    await interaction.followup.send(file=discord.File("leaderboard.png"))

@tasks.loop(minutes=3)  # Check every 3 minutes
async def reset_leaderboard():
    """Reset the leaderboard weekly."""
    global reset_time, study_times
    if datetime.now() >= reset_time:
        # Announce reset
        for guild in bot.guilds:  # Send to all servers the bot is in
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send("Weekly leaderboard has been reset! Log your study times for the new week!")
                    break
        # Reset times and update the next reset time
        study_times.clear()
        reset_time = datetime.now() + timedelta(weeks=1)

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

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} and slash commands are synced!")
    health_reminder.start()  # Start the task when the bot is ready
    reset_leaderboard.start()
    print(f'We have logged in as {bot.user}')

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
    /log_study [minutes] - Log your study time in minutes
    /show_leaderboard - Display the weekly study leaderboard
    """
    await interaction.followup.send(help_message)

# Run the bot
bot.run(TOKEN)
