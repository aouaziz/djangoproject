import asyncio
import json
import random
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Room, Game  # Make sure to import your models

connected_players = {}


class GameRoom(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Game state variables
        self.loop_interval = 0.03  # Interval in seconds (3ms)
        self.game_height = 600
        self.game_width = 1100
        self.game_running = False
        self.paddle1_speed = 0
        self.paddle2_speed = 0
        self._paddle1_y = 261  # Directly using private variables
        self._paddle2_y = 261  # Directly using private variables
        self.max_paddle_speed = 10
        self.paddle_width = 12
        self.paddle_height = 80
        self.ball_x = 544.5
        self.ball_y = 290.5
        self.max_ball_speed = 10
        self.ball_speed_x = 4
        self.ball_speed_y = 4
        self.ball_height = 15
        self.ball_width = 15
        self.player_id = None
        self.score1 = 0
        self.score2 = 0
        self.player1 = None
        self.player2 = None
        self.max_score = 5
        self.room_group_name = None
        self.printed = False
        self.game = None

    async def connect(self):
        room_code = self.scope['url_route']['kwargs']['room_code']
        await self.accept()
        try:
            room = await sync_to_async(Room.objects.get)(room_code=room_code)
        except Room.DoesNotExist:
            error_message = f"Unable to start game: Room with code {room_code} does not exist"
            print(error_message)
            await self.send_error(error_message)
            return
        if await sync_to_async(lambda: room.status)() == 'FINISH':
                error_message = f"Unable to start game: Room with code {room_code} has already finished."
                print(error_message)
                await self.send_error(error_message)
                return
        
        self.room_group_name = f"room_{room_code}"

        await self.channel_layer.group_add(
            self.room_group_name, self.channel_name
        )

        connected_players.setdefault(self.room_group_name, 0)
        connected_players[self.room_group_name] += 1

        if connected_players[self.room_group_name] == 1:
            self.player_id = "player1"
        elif connected_players[self.room_group_name] == 2:
            self.player_id = "player2"
        else:
            error_message = "Connection failed: Room is full"
            print(error_message)
            
            await self.send_error(error_message)
            return

        
        if connected_players[self.room_group_name] == 2:
            # Notify both players that the game is starting
            try:
                self.game = await sync_to_async(Game.objects.get)(room=room)
            except Game.DoesNotExist:
                error_message = "Unable to start game: No active game associated with this room."
                print(error_message)
                await self.send_error(error_message)
                return
            
            # Fetching player usernames asynchronously using sync_to_async
            self.player1 = await sync_to_async(lambda: self.game.player1.username)()
            self.player2 = await sync_to_async(lambda: self.game.player2.username)()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "send_message",
                    "message": "start_game",
                    "player1": self.player1,
                    "player2": self.player2,
                },
            )
            self.game_running = True
            asyncio.create_task(self.game_loop())

    async def disconnect(self, close_code):
        if self.game and self.game_running:
            # Determine the winner
            winner = self.player2 if self.player_id == "player1" else self.player1
            # Update game status
           # Notify players about the game over event
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "send_message",
                    "message": "game_over",
                    "payload": {
                        "message": f"Game Over! {winner} won due to opponent disconnection!",
                        "score1": self.score1,
                        "score2": self.score2,
                        "winner": winner,

                    },
                },
            )
            await sync_to_async(self.set_game_status(winner), thread_sensitive=True)()

        # Clean up connected players data for the room
        if self.room_group_name in connected_players:
            del connected_players[self.room_group_name]

        # Stop the game and leave the group
        self.game_running = False
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
             )
        print(f"Disconnect: code {close_code}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get("action")
            if action == "move":
                await self.handle_paddle_move(data)
        except json.JSONDecodeError:
            error_message = f"Invalid JSON received: {text_data}"
            print(error_message)
            await self.send_error(error_message)
            return

    async def handle_paddle_move(self, data):
        direction = data.get("direction")
        player = data.get("player")
        if player == "player1":
            await self.update_paddle1(direction)
        elif player == "player2":
            await self.update_paddle2(direction)

    async def update_paddle1(self, direction):
        if direction == "up":
            self.paddle1_speed = max(
                -self.max_paddle_speed, self.paddle1_speed - 4
            )
        elif direction == "down":
            self.paddle1_speed = min(
                self.max_paddle_speed, self.paddle1_speed + 4
            )
        else:# Deceleration logic: reduce speed smoothly to zero
            self.paddle1_speed = 0

        self._paddle1_y += self.paddle1_speed
        self._paddle1_y = max(
            0, min(self._paddle1_y, self.game_height - self.paddle_height)
        )
        # Send player move update
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "player_move",
                 "channel_name" : self.channel_name,
                 "paddle1_y": self._paddle1_y,
             }
        )

    async def update_paddle2(self, direction):
        if direction == "up":
            self.paddle2_speed = max(
                -self.max_paddle_speed, self.paddle2_speed - 4
            )
        elif direction == "down":
            self.paddle2_speed = min(
                self.max_paddle_speed, self.paddle2_speed + 4
            )
        else:# Deceleration logic: reduce speed smoothly to zero
            self.paddle2_speed = 0

        self._paddle2_y += self.paddle2_speed
        self._paddle2_y = max(
            0, min(self._paddle2_y, self.game_height - self.paddle_height)
        )

    def increase_ball_speed(self):
        if abs(self.ball_speed_y) < self.max_ball_speed:
            self.ball_speed_y *= 1.1  # Increase Y speed by 10%

        if abs(self.ball_speed_x) < self.max_ball_speed:
            self.ball_speed_x *= 1.1  # Increase X speed by 10%

    def reset_ball(self):
        """Reset the ball to the center with random direction."""
        self.ball_x = self.game_width / 2
        self.ball_y = self.game_height / 2

        self.ball_speed_x = 4 if random.randint(0, 100) % 2 == 0 else -4
        self.ball_speed_y = 4 if random.randint(0, 100) % 2 == 0 else -4

    async def game_loop(self):
        while self.game_running:
            self.update_ball_position()
            if self.score1 >= self.max_score or self.score2 >= self.max_score:
                 await self.end_game()
                 return
            # Broadcast game state
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "send_message",
                    "message": "game_update",
                    "payload": {
                        "paddle1_y": self._paddle1_y,  # Directly access the private variables
                        "paddle2_y": self._paddle2_y,  # Directly access the private variables
                        "ball_x": self.ball_x,
                        "ball_y": self.ball_y,
                        "score1": self.score1,
                        "score2": self.score2,
                    },
                },
            )
            await asyncio.sleep(self.loop_interval)

    def update_ball_position(self):
        # Ball collision with top/bottom walls
        if self.ball_y <= 0 or self.ball_y >= self.game_height - self.ball_height:
            self.ball_speed_y *= -1

        # Ball collision with Paddle1
        if (
            self.ball_x <= self.paddle_width
            and self.ball_y >= self._paddle1_y
            and self.ball_y <= self._paddle1_y + self.paddle_height
        ):
            self.ball_speed_x *= -1
            self.increase_ball_speed()

        # Ball collision with Paddle2
        if (
            self.ball_x >= self.game_width - self.paddle_width - self.ball_width
            and self.ball_y >= self._paddle2_y
            and self.ball_y <= self._paddle2_y + self.paddle_height
        ):
            self.ball_speed_x *= -1
            self.increase_ball_speed()

        self.ball_x += self.ball_speed_x
        self.ball_y += self.ball_speed_y

        # Ball out of bounds
        if self.ball_x <= 0:
            self.score2 += 1
            self.reset_ball()
            self.printed = True
        elif self.ball_x >= self.game_width - self.ball_width:
            self.score1 += 1
            self.reset_ball()
            self.printed = True
        if self.printed:
            print("player1 score : ", self.score1 ," player2 score : " , self.score2 )
            self.printed = False

    async def end_game(self):
        self.game_running = False
        if self.score1 > self.score2:
            winner = self.player1
        else:
            winner = self.player2
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "send_message",
                "message": "game_over",
                "payload": {
                    "message": f"Game Over! {winner} won!",
                    "score1": self.score1,
                    "score2": self.score2,
                    "winner": winner,
                },
            },
        )
        await sync_to_async(self.set_game_status(winner), thread_sensitive=True)()


    async def send_message(self, event):
            await self.send(text_data=json.dumps(event))


    
    async def send_error(self, message):
        try:
            await self.send(text_data=json.dumps({
                "error": True,  # Indicating there's an error
                "message": message
            }))
        except Exception as e:
            print(f"Failed to send error: {e}")
        await self.close()

    async def player_move(self, event):

        if self.channel_name == event.get("channel_name"):
            pass
        else:
            self._paddle1_y = int(event.get("paddle1_y"))

    def set_game_status(self,winner):
        self.game.room.status = 'FINISH'  # Set the status
        self.game.winner = winner  # Assign the winner
        self.game.save()  # Save the game object