import asyncio
import discord
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import random
from collections import defaultdict
import time
import io
from io import BytesIO
import requests
import re
import aiohttp
from keep_alive import keep_alive

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

# 1. Pomodoro Feature
user_timers = {}
work_times = defaultdict(int)

@bot.tree.command(name='pomodoro', description='Start a Pomodoro timer with custom durations.')
async def pomodoro_slash(interaction: discord.Interaction, work_minutes: int = 25, break_minutes: int = 5):
    """Start a Pomodoro timer with custom durations and updates every second."""
    user_id = str(interaction.user.id)

    if work_minutes <= 0:
        embed = discord.Embed(
            title="Invalid Input",
            description="Please enter a positive number for work minutes.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        return

    if break_minutes <= 0:
        break_minutes = 5  # Default break time

    max_chunk = 14 * 60  # Max 14-minute chunk (840 seconds)
    work_time = work_minutes * 60
    break_time = break_minutes * 60
    bar_length = 20

    # Initial Work Timer Embed
    embed = discord.Embed(
        title="Pomodoro Timer",
        description=f"Work for {work_minutes} minutes. Timer updates every second.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Pomodoro Timer in progress")

    await interaction.response.defer()
    message = await interaction.followup.send(embed=embed, wait=True)

    async def update_timer_embed(message, remaining_time, total_time, phase):
        """Update the embed progress bar dynamically."""
        try:
            minutes, seconds = divmod(remaining_time, 60)
            elapsed_time = total_time - remaining_time
            progress = elapsed_time / total_time
            filled_length = int(bar_length * progress)
            bar = "█" * filled_length + "–" * (bar_length - filled_length)

            embed = message.embeds[0]
            if phase == "Work":
                embed.description = f"Work Timer: [{bar}] {minutes:02d}:{seconds:02d}\nWork for {work_minutes} minutes."
            else:
                embed.description = f"Break Timer: [{bar}] {minutes:02d}:{seconds:02d}\nTake a break for {break_minutes} minutes."

            await message.edit(embed=embed)
            return message
        except discord.NotFound:
            print("Error: Message not found. It may have been deleted.")
            embed = discord.Embed(
                title="Timer Continues...",
                description="Timer is still running...",
                color=discord.Color.blue() if phase == "Work" else discord.Color.green()
            )
            embed.set_footer(text="Pomodoro Timer in progress")
            new_message = await message.channel.send(embed=embed)
            return new_message
        except discord.Forbidden:
            print("Error: Bot lacks permission to edit messages.")
        except discord.HTTPException as e:
            print(f"Error updating embed: {e}")
        return message

    async def start_timer(interaction, message, total_time, phase, user_id):
        """Run the Pomodoro timer in 14-minute chunks while updating the embed dynamically."""
        remaining_time = total_time
        start_time = int(time.time())
        thread = None

        user_timers[user_id] = asyncio.current_task()
        user_timers[user_id].start_time = start_time

        while remaining_time > 0:
            chunk_time = min(remaining_time, max_chunk)
            for _ in range(chunk_time):
                if remaining_time <= 0 or user_timers.get(user_id) is None:
                    return
                message = await update_timer_embed(message, remaining_time, total_time, phase)
                await asyncio.sleep(0.5)
                remaining_time -= 1

            if remaining_time > 0:
                new_embed = discord.Embed(
                    title=f"{phase} Timer Continues...",
                    description=f"Continue {phase.lower()}ing for the remaining time.",
                    color=discord.Color.blue() if phase == "Work" else discord.Color.green()
                )
                new_embed.set_footer(text="Pomodoro Timer in progress")

                if not thread and total_time > max_chunk:
                    thread_embed = discord.Embed(
                        title="Timer Continues in Thread",
                        description=f"To keep things organized, the timer will continue in a new thread. You can follow the updates there. Thank you :)",
                        color=discord.Color.blue()
                    )
                    await interaction.channel.send(embed=thread_embed)

                    thread = await interaction.channel.create_thread(
                        name=f"{interaction.user.display_name}'s {phase} Timer Thread", message=message
                    )
                    if thread:
                        message = await thread.send(embed=new_embed)
                    else:
                        print("Error: Failed to create thread.")
                else:
                    if thread:
                        message = await thread.send(embed=new_embed)
                    else:
                        message = await message.channel.send(embed=new_embed)

        end_time = int(time.time())
        elapsed_work_time = total_time
        if phase == "Work":
            work_times[user_id] += elapsed_work_time

        return message, thread

    # Stop previous timer if running
    if user_id in user_timers and user_timers[user_id] is not None:
        user_timers[user_id].cancel()
        user_timers[user_id] = None

    message, thread = await start_timer(interaction, message, work_time, "Work", user_id)

    embed = discord.Embed(
        title="Work Session Complete",
        description=f"**Work session complete! You worked for {work_minutes} minutes. It's time for a break. Don't forget to breathe :)** 🎉",
        color=discord.Color.green()
    )
    if thread:
        await thread.send(embed=embed)
    else:
        await message.channel.send(embed=embed)

    break_embed = discord.Embed(
        title="Break Timer",
        description=f"Take a break for {break_minutes} minutes. Timer updates every second.",
        color=discord.Color.blue()
    )
    break_embed.set_footer(text="Break Timer in progress")
    if thread:
        break_message = await thread.send(embed=break_embed)
    else:
        break_message = await message.channel.send(embed=break_embed)
    message, _ = await start_timer(interaction, break_message, break_time, "Break", user_id)

    embed = discord.Embed(
        title="Break Over",
        description="**You've completed a Pomodoro session! Great job buddy :)** ✅",
        color=discord.Color.green()
    )
    if thread:
        await thread.send(embed=embed)
    else:
        await message.channel.send(embed=embed)

@bot.tree.command(name='stop_timer', description='Stop the Pomodoro timer if it is running.')
async def stop_timer(interaction: discord.Interaction):
    """Stop the Pomodoro timer if running."""
    user_id = str(interaction.user.id)
    if user_id in user_timers and user_timers[user_id] is not None:
        user_timers[user_id].cancel()
        elapsed_work_time = int(time.time()) - user_timers[user_id].start_time
        work_times[user_id] += elapsed_work_time
        user_timers[user_id] = None

        embed = discord.Embed(
            title="Pomodoro Timer Stopped",
            description=f"The timer has been stopped successfully. You worked for {elapsed_work_time // 60} minutes.",
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

# 2. To-Do List Feature
to_do_list = defaultdict(list)

@bot.tree.command(name='add_task', description='Add a task to your to-do list')
async def add_task_slash(interaction: discord.Interaction, task: str):
    """Adds a task to the user's personal to-do list."""
    user_id = str(interaction.user.id)
    tasks = task.split(',')
    for task in tasks:
        to_do_list[user_id].append((task.strip(), False))  # Add tasks as "not done"
    
    tasks_display = "\n".join([f"{i + 1}. {t[0]} {'✅' if t[1] else ''}" for i, t in enumerate(to_do_list[user_id])])
    embed = discord.Embed(title="To-Do List Update", description=f"Added tasks:\n{tasks_display}", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='show_tasks', description='Show all tasks in your to-do list')
async def show_tasks_slash(interaction: discord.Interaction):
    """Shows all tasks in the user's personal to-do list."""
    user_id = str(interaction.user.id)
    if user_id not in to_do_list or not to_do_list[user_id]:
        embed = discord.Embed(title="To-Do List", description="Your to-do list is empty!", color=discord.Color.blue())
    else:
        total_tasks = len(to_do_list[user_id])
        completed_tasks = sum(1 for task in to_do_list[user_id] if task[1])
        completion_percentage = (completed_tasks / total_tasks) * 100

        tasks_list = "\n".join([f"{i + 1}. {task[0]} {'✅' if task[1] else ''}" for i, task in enumerate(to_do_list[user_id])])
        embed = discord.Embed(
            title="To-Do List",
            description=f"Your to-do list:\n{tasks_list}\n\n**Completion: {completion_percentage:.2f}%**",
            color=discord.Color.blue()
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_tasks", description="Remove multiple tasks by their numbers.")
async def remove_tasks_slash(interaction: discord.Interaction, indexes: str):
    user_id = str(interaction.user.id)
    try:
        index_list = sorted([int(i) for i in re.split('[, ]+', indexes) if i.strip()], reverse=True)
        if user_id not in to_do_list or any(not (1 <= i <= len(to_do_list[user_id])) for i in index_list):
            embed = discord.Embed(title="Error", description="Invalid task numbers! Make sure the numbers are within the range of your tasks.", color=discord.Color.red())
        else:
            removed_tasks = []
            for index in index_list:
                removed_task = to_do_list[user_id].pop(index - 1)
                removed_tasks.append(removed_task[0])
            embed = discord.Embed(title="To-Do List Update", description=f"Removed tasks: {', '.join(removed_tasks)}", color=discord.Color.blue())
    except (IndexError, ValueError):
        embed = discord.Embed(title="Error", description="Invalid task numbers! Please enter valid integers for the task indexes separated by spaces or commas.", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='mark_tasks_done', description='Mark multiple tasks as done by their numbers.')
async def mark_tasks_done_slash(interaction: discord.Interaction, indexes: str):
    user_id = str(interaction.user.id)
    try:
        index_list = sorted([int(i) for i in re.split('[, ]+', indexes) if i.strip()], reverse=True)
        if user_id not in to_do_list or any(not (1 <= i <= len(to_do_list[user_id])) for i in index_list):
            embed = discord.Embed(title="Error", description="Invalid task numbers! Make sure the numbers are within the range of your tasks.", color=discord.Color.red())
        else:
            marked_tasks = []
            for index in index_list:
                task, _ = to_do_list[user_id][index - 1]
                to_do_list[user_id][index - 1] = (task, True)
                marked_tasks.append(task)

            # Check if all tasks are completed
            if all(task[1] for task in to_do_list[user_id]):
                completed_tasks = "\n".join([f"{i + 1}. {task[0]} {'✅'}" for i, task in enumerate(to_do_list[user_id])])
                embed = discord.Embed(
                    title="To-Do List Completed",
                    description=f"Congratulations! All tasks have been completed:\n{completed_tasks}\n\nYour to-do list has been cleared. Feel free to add new tasks!",
                    color=discord.Color.green()
                )
                to_do_list[user_id].clear()
            else:
                embed = discord.Embed(
                    title="To-Do List Update",
                    description=f"Marked tasks: {', '.join(marked_tasks)} as done ✅. Look at you finishing those tasks, good luck with your other tasks :)",
                    color=discord.Color.green()
                )
    except (IndexError, ValueError):
        embed = discord.Embed(
            title="Error",
            description="Invalid task numbers! Please enter valid integers for the task indexes separated by spaces or commas.",
            color=discord.Color.red()
        )
    await interaction.response.send_message(embed=embed)

# 3. Study Tracker Feature
study_times = defaultdict(int)
voice_channel_start_times = {}

# Configuration for tracked voice channels
tracked_channels = set()  # Set of channel IDs that the bot will track

# Specify the channel ID for automatic announcements and resets
announcement_channel_id = 10  # Replace with your specific channel ID

# Weekly Reset Timer (Set the initial reset time to Monday 00:00 UTC)
now = datetime.now(timezone.utc)
next_monday = now + timedelta(days=(7 - now.weekday()) % 7)
reset_time = datetime(next_monday.year, next_monday.month, next_monday.day, 0, 0, tzinfo=timezone.utc)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    user_id = str(member.id)
    
    if before.channel != after.channel:
        # User leaves a tracked voice channel or moves to an untracked voice channel
        if before.channel and before.channel.id in tracked_channels:
            print(f"{member.name} left tracked channel {before.channel.id}")
            if user_id in voice_channel_start_times:
                start_time = voice_channel_start_times.pop(user_id)
                elapsed_minutes = (datetime.now(timezone.utc) - start_time).total_seconds() // 60
                study_times[user_id] += int(elapsed_minutes)
                print(f"Added {int(elapsed_minutes)} minutes to {member.name}'s study time")
            else:
                print(f"{member.name} was not tracked in {before.channel.id}")

        # User joins a tracked voice channel
        if after.channel and after.channel.id in tracked_channels:
            print(f"{member.name} joined tracked channel {after.channel.id}")
            voice_channel_start_times[user_id] = datetime.now(timezone.utc)
        else:
            print(f"{member.name} joined an untracked or no channel")

@bot.tree.command(name='log_study', description='Check your total Pomodoro study time')
async def log_study_slash(interaction: discord.Interaction):
    """Check your total Pomodoro study time."""
    user_id = str(interaction.user.id)
    total_pomodoro_time = work_times[user_id] // 60

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
        room_id_int = int(room_id)
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
        room_id_int = int(room_id)
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
    
    for user_id, work_time in work_times.items():
        combined_times[user_id] += work_time // 60
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

@tasks.loop(minutes=1)
async def reset_leaderboard():
    """Reset the leaderboard every week at Monday 00:00 UTC."""
    global reset_time, study_times, work_times
    now_utc = datetime.now(timezone.utc)
    if now_utc >= reset_time:
        print(f"Resetting leaderboard at {now_utc}")
        channel = bot.get_channel(announcement_channel_id)
        if channel and channel.permissions_for(channel.guild.me).send_messages:
            await send_leaderboard(channel)
            await channel.send(embed=discord.Embed(
                title="Weekly Leaderboard Reset",
                description="Weekly leaderboard has been reset! Log your study times for the new week!",
                color=discord.Color.blue()
            ))
            study_times.clear()
            work_times.clear()
        reset_time = now_utc + timedelta(weeks=1)  # Reset every week at Monday 00:00 UTC

# 4. Motivational Messages Feature
channel_ids = [10, 10, 10]  # Just add commas to add another channel for motivation and health reminder

last_motivational_quote = None
last_health_reminder = None

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

@tasks.loop(hours=3) # Adjust interval as needed
async def motivational_quotes_loop():
    global last_motivational_quote
    for channel_id in channel_ids:
        channel = bot.get_channel(channel_id)
        if channel:
            if random.choice([True, False]):
                new_quote = random.choice(motivational_quotes)
            else:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://zenquotes.io/api/random") as response:
                            data = await response.json()
                            new_quote = data[0]['q'] + " -" + data[0]['a'] + " ✨"
                except Exception as e:
                    new_quote = "You are amazing! Keep believing in yourself. 🌟"
                    print(f"Error fetching quote: {e}")

            while new_quote == last_motivational_quote:
                new_quote = random.choice(motivational_quotes)
                
                if random.choice([True, False]):
                    new_quote = random.choice(motivational_quotes)
                else:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get("https://zenquotes.io/api/random") as response:
                                data = await response.json()
                                new_quote = data[0]['q'] + " -" + data[0]['a'] + " ✨"
                    except Exception as e:
                        new_quote = "You are amazing! Keep believing in yourself. 🌟"  # Fallback quote
                        print(f"Error fetching quote: {e}")

            last_motivational_quote = new_quote

            embed = discord.Embed(
                title="Motivational Quote",
                description=new_quote,
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)

@bot.tree.command(name='motivate', description='Get a motivational message')
async def motivate_slash(interaction: discord.Interaction):
    global last_motivational_quote
    if random.choice([True, False]):
        new_quote = random.choice(motivational_quotes)
    else:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://zenquotes.io/api/random") as response:
                    data = await response.json()
                    new_quote = data[0]['q'] + " -" + data[0]['a'] + " ✨"
        except Exception as e:
            new_quote = "You are amazing! Keep believing in yourself. 🌟"
            print(f"Error fetching quote: {e}")

    # Ensure the new quote is different from the last one
    while new_quote == last_motivational_quote:
        new_quote = random.choice(motivational_quotes)
        
        if random.choice([True, False]):
            new_quote = random.choice(motivational_quotes)
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://zenquotes.io/api/random") as response:
                        data = await response.json()
                        new_quote = data[0]['q'] + " -" + data[0]['a'] + " ✨"
            except Exception as e:
                new_quote = "You are amazing! Keep believing in yourself. 🌟"  # Fallback quote
                print(f"Error fetching quote: {e}")

    last_motivational_quote = new_quote

    embed = discord.Embed(
        title="Motivational Quote :)",
        description=new_quote,
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)

# 5. Health Reminders Feature
reminders = [
    "Time to drink some water! 💧",
    "Take a deep breath and relax. 🌬️",
    "Fix your posture! Sit up straight. 🪑",
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
    "Stretch your neck gently side to side. 🧘",
    "Relax your shoulders. Let go of any tension. 🫂",
    "Take a moment to smile! 😊",
    "Wash your hands if you haven’t in a while. 🧼",
    "Stand up and do 10 squats! 🏋️",
    "Take a deep breath and count to five. 🌬️",
    "Do a quick wrist stretch to avoid strain. ✋",
    "Close your eyes for 20 seconds to relax them. 😌",
    "Check your surroundings for a moment of mindfulness. 🌱",
    "Take a sip of your favorite tea or coffee. ☕",
    "Write down something you're grateful for today. 📓",
    "Let your eyes wander and notice something beautiful. 🌸",
    "Open a window for some fresh air. 🌬️",
    "Add some green plants to your workspace for a fresh vibe. 🌿",
    "Do a quick shoulder roll exercise. 🔄",
    "Keep a glass of water handy and sip frequently. 💧",
    "Check your ergonomics: is your chair and desk setup comfortable? 🪑",
    "Step outside for a breath of fresh air. 🌤️",
    "Play your favorite calming music for 5 minutes. 🎶",
    "Take a moment to appreciate yourself—you’re doing great! 🌟",
    "Massage your temples or the back of your neck. 💆",
    "Roll your ankles in small circles for better blood flow. 🔄",
    "Take a 5-minute break to rest your mind. 🌻",
    "Eat a piece of fruit for a healthy energy boost. 🍓",
    "Organize your desk to create a more focused workspace. 📚",
    "Drink a glass of water before you continue working. 💧",
    "Take three slow, deep breaths to reset. 🌬️",
    "Shake out your arms and legs to release tension. 🤲",
    "Have a quick stretch or walk—it’s good for your back. 🚶",
    "Take a quick mindfulness pause and notice 3 things around you. 🧘",
    "Journal one positive thought or goal for the day. 📝",
    "Do a quick hand massage to relax your fingers. 🤲",
    "Look outside for a moment and connect with nature. 🌳",
    "Lightly tap your shoulders and upper back for better circulation. 🖐️",
    "Tidy up your immediate space—it helps your mental clarity. 🧹",
    "Switch up your sitting position to avoid stiffness. 🪑",
    "Give your wrists a gentle shake to release tension. ✋",
    "Place your palms together and stretch your fingers outward. 🤝",
    "Take a mindful sip of water and enjoy its refreshment. 💦"
]

@tasks.loop(hours=6)  # Adjust interval as needed
async def health_reminder():
    global last_health_reminder
    for channel_id in channel_ids:
        channel = bot.get_channel(channel_id)
        if channel:
            new_reminder = random.choice(reminders)

            while new_reminder == last_health_reminder:
                new_reminder = random.choice(reminders)

            last_health_reminder = new_reminder

            embed = discord.Embed(
                title="Health Reminder",
                description=new_reminder,
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)

@bot.tree.command(name="health_reminder", description="Get a health reminder")
async def health_reminder_command(interaction: discord.Interaction):
    global last_health_reminder
    new_reminder = random.choice(reminders)

    # Ensure the new reminder is different from the last one
    while new_reminder == last_health_reminder:
        new_reminder = random.choice(reminders)

    last_health_reminder = new_reminder

    embed = discord.Embed(
        title="Health Reminder",
        description=new_reminder,
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

# 6. Cat :3
CATAAS_API_URL = "https://cataas.com/cat"
CATAAS_GIF_API_URL = "https://cataas.com/cat/gif"

MEOW_FACTS_API_URL = "https://meowfacts.herokuapp.com/"

@bot.tree.command(name='cat', description='Get a random funny cat image or GIF and a cat fact')
async def cat(interaction: discord.Interaction):
    """Send a random funny cat image or GIF and a cat fact."""
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(MEOW_FACTS_API_URL) as cat_fact_response:
                cat_fact_response.raise_for_status()
                cat_fact_data = await cat_fact_response.json()
                cat_fact = cat_fact_data["data"][0] + " 🐾🐱"
                print("Fetched cat fact:", cat_fact)
            
            if random.choice([True, False]):
                async with session.get(CATAAS_API_URL) as cat_media_response:
                    cat_media_response.raise_for_status()
                    cat_media_data = await cat_media_response.read()
                    cat_media_url = CATAAS_API_URL
                    cat_media_content = BytesIO(cat_media_data)
                    cat_media_file = discord.File(cat_media_content, filename="cat_image.jpg")
                    print("Fetched cat image")
            else:
                async with session.get(CATAAS_GIF_API_URL) as cat_media_response:
                    cat_media_response.raise_for_status()
                    cat_media_data = await cat_media_response.read()
                    cat_media_url = CATAAS_GIF_API_URL
                    cat_media_content = BytesIO(cat_media_data)
                    cat_media_file = discord.File(cat_media_content, filename="cat_gif.gif")
                    print("Fetched cat GIF")
                    
        except aiohttp.ClientError as e:
            cat_media_url = "https://cataas.com/cat"
            cat_fact = "Did you know? Cats have five toes on their front paws, but only four on their back paws. 🐾🐱"
            cat_media_file = None
            print(f"Error fetching data: {e}")

    embed = discord.Embed(title="🐱 Silly Cats Time :3 🐱", color=discord.Color.blue())
    embed.add_field(name="A Lil Cat Fun Fact", value=cat_fact, inline=False)

    if cat_media_file:
        await interaction.followup.send(embed=embed, file=cat_media_file)
    else:
        embed.set_image(url=cat_media_url)
        await interaction.followup.send(embed=embed)

# 7. Help Commands
@bot.tree.command(name='help', description='Shows available commands')
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Help Commands",
        description="Here are the commands you can use:",
        color=discord.Color.blue()
    )

    embed.add_field(name="/pomodoro [work_minutes] [break_minutes]", value="Start a Pomodoro timer (default 25 work, 5 break)", inline=False)
    embed.add_field(name="/add_task [task]", value="Add a task to your to-do list (Use comma to add more than one tasks)", inline=False)
    embed.add_field(name="/show_tasks", value="Show your current to-do list", inline=False)
    embed.add_field(name="/remove_task [task_number]", value="Remove a task from your to-do list by its number (Use comma to delete multiple tasks)", inline=False)
    embed.add_field(name="/motivate", value="Get a motivational message", inline=False)
    embed.add_field(name="/health_reminder", value="Receive health reminders every 30 minutes (running in the background)", inline=False)
    embed.add_field(name="/log_study", value="Check your total Pomodoro study time", inline=False)
    embed.add_field(name="/show_leaderboard", value="Display the weekly study leaderboard", inline=False)
    embed.add_field(name="/mark_tasks_done", value="Mark your tasks as finish (Use comma to mark multiple tasks)", inline=False)
    embed.add_field(name="/cat", value="Get a random funny cat image or GIF with a cat fact hehehe :)", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    global bot_start_time
    bot_start_time = datetime.now(timezone.utc)

    await bot.tree.sync()
    print(f"Logged in as {bot.user} and slash commands are synced!")
    health_reminder.start()
    motivational_quotes_loop.start()
    reset_leaderboard.start()
    print(f'We have logged in as {bot.user}')

# Call keep_alive to start the server
keep_alive()

# Run the bot
bot.run(TOKEN)
