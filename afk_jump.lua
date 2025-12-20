-- AFK Auto Jump GUI (Mobile / Delta) - FIXED DRAG

local Players = game:GetService("Players")
local UIS = game:GetService("UserInputService")
local StarterGui = game:GetService("StarterGui")
local player = Players.LocalPlayer

-- Notification
pcall(function()
    StarterGui:SetCore("SendNotification", {
        Title = "سكربت علاوي",
        Text = "تم تفعيل السكربت بنجاح ✅",
        Duration = 5
    })
end)

-- GUI
local gui = Instance.new("ScreenGui")
gui.Parent = player:WaitForChild("PlayerGui")
gui.ResetOnSpawn = false

local frame = Instance.new("Frame", gui)
frame.Size = UDim2.new(0, 90, 0, 35)
frame.Position = UDim2.new(0.5, -45, 0.5, -17)
frame.BackgroundColor3 = Color3.fromRGB(0,0,0)
frame.BorderSizePixel = 0
frame.Active = true -- مهم

local button = Instance.new("TextButton", frame)
button.Size = UDim2.new(1,0,1,0)
button.BackgroundTransparency = 1
button.Text = "ON"
button.TextScaled = true
button.Font = Enum.Font.GothamBold
button.TextColor3 = Color3.fromRGB(0,255,0)

-- Drag logic (Mobile safe)
local dragging = false
local dragStart, startPos

frame.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.Touch then
        dragging = true
        dragStart = input.Position
        startPos = frame.Position
    end
end)

frame.InputEnded:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.Touch then
        dragging = false
    end
end)

UIS.InputChanged:Connect(function(input)
    if dragging and input.UserInputType == Enum.UserInputType.Touch then
        local delta = input.Position - dragStart
        frame.Position = UDim2.new(
            startPos.X.Scale,
            startPos.X.Offset + delta.X,
            startPos.Y.Scale,
            startPos.Y.Offset + delta.Y
        )
    end
end)

-- AFK Logic
local enabled = true

button.MouseButton1Click:Connect(function()
    enabled = not enabled
    if enabled then
        button.Text = "ON"
        button.TextColor3 = Color3.fromRGB(0,255,0)
    else
        button.Text = "OFF"
        button.TextColor3 = Color3.fromRGB(255,0,0)
    end
end)

task.spawn(function()
    while true do
        task.wait(math.random(60,300))
        if enabled then
            local char = player.Character
            if char then
                local hum = char:FindFirstChildOfClass("Humanoid")
                if hum then
                    hum:ChangeState(Enum.HumanoidStateType.Jumping)
                end
            end
        end
    end
end)
