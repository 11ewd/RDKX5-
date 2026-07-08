/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body - Car/Pump/PCA9685 Servo + TIM12 Gimbal Servo Version
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "i2c.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

typedef struct
{
    int16_t pwm_cmd;          // 当前输出PWM命令（-8399~8399）
    int16_t enc_delta_10ms;   // 10ms编码器增量
    int32_t enc_total;        // 累计编码器计数
} MotorState_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* -------------------- 硬件参数 -------------------- */
#define MOTOR_PWM_MAX              8399

/* 普通前进/后退速度：原来 MOTOR_TEST_PWM=1500，对重车偏小 */
#define MOTOR_MOVE_PWM             1500

/* 转弯持续速度：车重转不动就优先调大这个值 */
#define MOTOR_TURN_PWM             3500

/* 转弯起步冲击速度：先大力冲一下，克服静摩擦 */
#define MOTOR_TURN_START_PWM       3500

/* 转弯起步冲击时间，单位 ms */
#define MOTOR_TURN_START_TIME_MS   0

/*
    舵机脉宽范围：
    500us  -> 约0°
    1500us -> 约90°
    2500us -> 约180°

    如果舵机有异响、顶死、发热，可以改成：
    SERVO_MIN_US = 700
    SERVO_MAX_US = 2300
*/
#define SERVO_MIN_US               500
#define SERVO_MID_US               1500
#define SERVO_MAX_US               2700


/* -------------------- 调试选项 -------------------- */
#define DEBUG_PRINT_ENABLE         0

/* -------------------- PCA9685 参数 -------------------- */
#define PCA9685_ADDR               (0x40 << 1)   // HAL库使用8位地址，所以0x40左移1位
#define PCA9685_MODE1              0x00
#define PCA9685_MODE2              0x01
#define PCA9685_LED0_ON_L          0x06
#define PCA9685_PRESCALE           0xFE

#define PCA9685_SERVO_FREQ         50            // 舵机PWM频率50Hz

#define PCA9685_CH_BOTTOM          0             // CH0 -> 最底下舵机
#define PCA9685_CH_MIDDLE          1             // CH1 -> 中间舵机
#define PCA9685_CH_TOP             2             // CH2 -> 最上面舵机

/* -------------------- 引脚映射 -------------------- */
/* 电机方向控制 */
#define M1_IN1_GPIO_Port           GPIOD
#define M1_IN1_Pin                 GPIO_PIN_0
#define M1_IN2_GPIO_Port           GPIOD
#define M1_IN2_Pin                 GPIO_PIN_1

#define M2_IN1_GPIO_Port           GPIOD
#define M2_IN1_Pin                 GPIO_PIN_2
#define M2_IN2_GPIO_Port           GPIOD
#define M2_IN2_Pin                 GPIO_PIN_3

#define M3_IN1_GPIO_Port           GPIOD
#define M3_IN1_Pin                 GPIO_PIN_4
#define M3_IN2_GPIO_Port           GPIOD
#define M3_IN2_Pin                 GPIO_PIN_5

#define M4_IN1_GPIO_Port           GPIOD
#define M4_IN1_Pin                 GPIO_PIN_6
#define M4_IN2_GPIO_Port           GPIOD
#define M4_IN2_Pin                 GPIO_PIN_7

#define MOTOR_EN_GPIO_Port         GPIOD
#define MOTOR_EN_Pin               GPIO_PIN_8

/* 两个水泵 */
#define PUMP1_GPIO_Port            GPIOC
#define PUMP1_Pin                  GPIO_PIN_4
#define PUMP2_GPIO_Port            GPIOC
#define PUMP2_Pin                  GPIO_PIN_5

/*
    你的继电器/驱动模块有 NO、NC、COM、VCC、GND、IN。
    多数这种模块是低电平触发：IN=0 吸合，IN=1 断开。
    如果你测试发现水泵逻辑反了，把对应的 1 改成 0。
*/
#define PUMP1_ACTIVE_LOW           0
#define PUMP2_ACTIVE_LOW           0

/* 状态灯/蜂鸣器 */
#define RUN_LED_GPIO_Port          GPIOD
#define RUN_LED_Pin                GPIO_PIN_12
#define FAULT_LED_GPIO_Port        GPIOD
#define FAULT_LED_Pin              GPIO_PIN_13
#define BEEP_GPIO_Port             GPIOD
#define BEEP_Pin                   GPIO_PIN_14
#define COMM_LED_GPIO_Port         GPIOD
#define COMM_LED_Pin               GPIO_PIN_15

/* 输入 */
#define ESTOP_GPIO_Port            GPIOE
#define ESTOP_Pin                  GPIO_PIN_0
#define LEVEL_GPIO_Port            GPIOE
#define LEVEL_Pin                  GPIO_PIN_1
#define LIMIT1_GPIO_Port           GPIOE
#define LIMIT1_Pin                 GPIO_PIN_2
#define LIMIT2_GPIO_Port           GPIOE
#define LIMIT2_Pin                 GPIO_PIN_3

/* 三个舵机编号：PCA9685 三路舵机，保持你原来的 L/R/Z 动作 */
#define SERVO_BOTTOM_ID            1
#define SERVO_MIDDLE_ID            2
#define SERVO_TOP_ID               3

/*
    新增：摄像头二自由度云台舵机
    PB14 -> TIM12_CH1 -> 云台水平 Yaw 舵机
    PB15 -> TIM12_CH2 -> 云台俯仰 Pitch 舵机

    注意：
    1. CubeMX 中 PB14 配 TIM12_CH1，PB15 配 TIM12_CH2。
    2. TIM12 要配置成 50Hz PWM，最好 1us 计数。
       如果当前系统时钟仍是 HSI 16MHz：
          Prescaler = 15
          Counter Period = 19999
          Pulse = 1500
       如果你的工程是 84MHz 定时器时钟：
          Prescaler = 83
          Counter Period = 19999
          Pulse = 1500
    3. 舵机外接 5V 供电，外部 5V GND 必须和 STM32 GND 共地。
*/
#define GIMBAL_YAW_LEFT_ANGLE      45
#define GIMBAL_YAW_CENTER_ANGLE    90
#define GIMBAL_YAW_RIGHT_ANGLE     135

#define GIMBAL_PITCH_UP_ANGLE      110
#define GIMBAL_PITCH_DEFAULT_ANGLE 80
#define GIMBAL_PITCH_DOWN_ANGLE    55

#define GIMBAL_MIN_US              500
#define GIMBAL_MAX_US              2500

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
#define CLAMP(x, low, high)   ((x) < (low) ? (low) : ((x) > (high) ? (high) : (x)))
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

static uint8_t uart2_rx_byte = 0;
static volatile uint8_t g_uart_cmd_pending = 0;

static char uart_tx_buf[360];

static MotorState_t g_motor[4];

static int16_t  enc_last_raw[4] = {0};

/*
    现在只使用 3 个舵机：
    g_servo_us[0] -> 最底下舵机，PCA9685_CH0
    g_servo_us[1] -> 中间舵机，  PCA9685_CH1
    g_servo_us[2] -> 最上面舵机，PCA9685_CH2
*/
static uint16_t g_servo_us[3] = {
    SERVO_MIN_US,
    SERVO_MIN_US,
    SERVO_MIN_US
};

/*
    新增云台舵机当前脉宽记录：
    g_gimbal_yaw_us   -> PB14 / TIM12_CH1
    g_gimbal_pitch_us -> PB15 / TIM12_CH2
*/
static uint16_t g_gimbal_yaw_us   = SERVO_MID_US;
static uint16_t g_gimbal_pitch_us = SERVO_MID_US;

static uint8_t  g_pump1_on      = 0;
static uint8_t  g_pump2_on      = 0;
static uint8_t  g_estop_latched = 0;
static uint8_t  g_fault_flag    = 0;


/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

static void User_SetSafeState(void);
static void User_StartPeripherals(void);
static void User_Beep(uint16_t ms);

static void App_Init(void);
static void App_Loop(void);

static void User_SendText(const char *str);
static void User_SendHelp(void);
static void User_SendStatus(void);
static void User_HandleUartByte(uint8_t ch);

static void Motor_Enable(uint8_t en);
static void Motor_SetPWM(uint8_t motor_id, int16_t pwm);
static void Motor_StopAll(void);

static void Car_Forward(void);
static void Car_Backward(void);
static void Car_TurnLeft(void);
static void Car_TurnRight(void);

static void PCA9685_Write8(uint8_t reg, uint8_t data);
static uint8_t PCA9685_Read8(uint8_t reg);
static uint8_t PCA9685_IsReady(void);
static void PCA9685_SetPWMFreq(uint16_t freq_hz);
static void PCA9685_SetPWM(uint8_t channel, uint16_t on, uint16_t off);
static void PCA9685_SetServoUs(uint8_t channel, uint16_t pulse_us);
static void PCA9685_Init(void);

static uint16_t Servo_AngleToUs(uint8_t angle);
static void Servo_SetUs(uint8_t servo_id, uint16_t pulse_us);
static void Servo_SetAngle(uint8_t servo_id, uint8_t angle);
static void Servo_InitPose(void);
static void Servo_ActionLeft(void);
static void Servo_ActionRight(void);
static void Servo_Reset(void);

static uint16_t Gimbal_AngleToUs(uint8_t angle);
static void Gimbal_SetYawUs(uint16_t pulse_us);
static void Gimbal_SetPitchUs(uint16_t pulse_us);
static void Gimbal_SetYawAngle(uint8_t angle);
static void Gimbal_SetPitchAngle(uint8_t angle);
static void Gimbal_InitPose(void);
static void Gimbal_LookLeft(void);
static void Gimbal_LookRight(void);
static void Gimbal_LookCenter(void);
static void Gimbal_PitchUp(void);
static void Gimbal_PitchDown(void);
static void Gimbal_PitchDefault(void);

static void Pump_GPIO_Init(void);
static void Pump1_On(void);
static void Pump1_Off(void);
static void Pump2_On(void);
static void Pump2_Off(void);

static int16_t Encoder_ReadRaw16(TIM_HandleTypeDef *htim);
static int16_t Encoder_ReadDelta(TIM_HandleTypeDef *htim, int16_t *last_raw);
static void Encoder_Update10ms(void);

static void Safety_Check(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

static void User_SendText(const char *str)
{
    HAL_UART_Transmit(&huart2, (uint8_t *)str, strlen(str), 100);
}

static void User_Beep(uint16_t ms)
{
    HAL_GPIO_WritePin(BEEP_GPIO_Port, BEEP_Pin, GPIO_PIN_SET);
    HAL_Delay(ms);
    HAL_GPIO_WritePin(BEEP_GPIO_Port, BEEP_Pin, GPIO_PIN_RESET);
}

static void User_SetSafeState(void)
{
    HAL_GPIO_WritePin(M1_IN1_GPIO_Port, M1_IN1_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M1_IN2_GPIO_Port, M1_IN2_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M2_IN1_GPIO_Port, M2_IN1_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M2_IN2_GPIO_Port, M2_IN2_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M3_IN1_GPIO_Port, M3_IN1_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M3_IN2_GPIO_Port, M3_IN2_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M4_IN1_GPIO_Port, M4_IN1_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(M4_IN2_GPIO_Port, M4_IN2_Pin, GPIO_PIN_RESET);

    /* 两个水泵安全关闭：兼容低电平触发/高电平触发模块 */
#if PUMP1_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_RESET);
#endif

#if PUMP2_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_RESET);
#endif

    g_pump1_on = 0;
    g_pump2_on = 0;

    HAL_GPIO_WritePin(RUN_LED_GPIO_Port, RUN_LED_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(FAULT_LED_GPIO_Port, FAULT_LED_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(BEEP_GPIO_Port, BEEP_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(COMM_LED_GPIO_Port, COMM_LED_Pin, GPIO_PIN_RESET);

    HAL_GPIO_WritePin(MOTOR_EN_GPIO_Port, MOTOR_EN_Pin, GPIO_PIN_RESET);

    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, 0);
    __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, 0);

    /* 新增 TIM12 云台舵机先关闭输出，启动外设后再给默认角度 */
    __HAL_TIM_SET_COMPARE(&htim12, TIM_CHANNEL_1, 0);
    __HAL_TIM_SET_COMPARE(&htim12, TIM_CHANNEL_2, 0);
}

static void User_StartPeripherals(void)
{
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_4);

    /*
        新增两个摄像头云台舵机：
        PB14 -> TIM12_CH1 -> Yaw 水平舵机
        PB15 -> TIM12_CH2 -> Pitch 俯仰舵机
    */
    HAL_TIM_PWM_Start(&htim12, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim12, TIM_CHANNEL_2);

    /*
        现在原来的三个执行机构舵机使用 PCA9685 控制，
        TIM12 只负责新增的摄像头云台两个舵机。
    */

    HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
    HAL_TIM_Encoder_Start(&htim3, TIM_CHANNEL_ALL);
    HAL_TIM_Encoder_Start(&htim4, TIM_CHANNEL_ALL);
    HAL_TIM_Encoder_Start(&htim8, TIM_CHANNEL_ALL);

    __HAL_TIM_SET_COUNTER(&htim2, 0);
    __HAL_TIM_SET_COUNTER(&htim3, 0);
    __HAL_TIM_SET_COUNTER(&htim4, 0);
    __HAL_TIM_SET_COUNTER(&htim8, 0);

    enc_last_raw[0] = 0;
    enc_last_raw[1] = 0;
    enc_last_raw[2] = 0;
    enc_last_raw[3] = 0;

    /*
        初始化 PCA9685：
        STM32F407VET6 使用 I2C2：
        PB10 -> SCL
        PB11 -> SDA
    */
    PCA9685_Init();

    /*
        上电初始角度：
        1. 原来的三个 PCA9685 舵机复位
        2. 新增摄像头云台回中、默认俯仰
    */
    Servo_InitPose();
    Gimbal_InitPose();

    HAL_UART_Receive_IT(&huart2, &uart2_rx_byte, 1);

    Motor_Enable(1);
}

/* -------------------- PCA9685 驱动部分 -------------------- */

static void PCA9685_Write8(uint8_t reg, uint8_t data)
{
    HAL_I2C_Mem_Write(&hi2c2,
                      PCA9685_ADDR,
                      reg,
                      I2C_MEMADD_SIZE_8BIT,
                      &data,
                      1,
                      100);
}

static uint8_t PCA9685_Read8(uint8_t reg)
{
    uint8_t data = 0;

    HAL_I2C_Mem_Read(&hi2c2,
                     PCA9685_ADDR,
                     reg,
                     I2C_MEMADD_SIZE_8BIT,
                     &data,
                     1,
                     100);

    return data;
}

static uint8_t PCA9685_IsReady(void)
{
    if (HAL_I2C_IsDeviceReady(&hi2c2, PCA9685_ADDR, 3, 100) == HAL_OK)
    {
        return 1;
    }
    else
    {
        return 0;
    }
}

static void PCA9685_SetPWMFreq(uint16_t freq_hz)
{
    uint8_t oldmode;
    uint8_t newmode;
    uint8_t prescale;

    /*
        PCA9685内部时钟约25MHz。
        prescale = 25000000 / (4096 * freq) - 1
        50Hz时 prescale 约等于121。
    */
    prescale = (uint8_t)(25000000UL / (4096UL * freq_hz) - 1);

    oldmode = PCA9685_Read8(PCA9685_MODE1);
    newmode = (oldmode & 0x7F) | 0x10;       // sleep

    PCA9685_Write8(PCA9685_MODE1, newmode);
    PCA9685_Write8(PCA9685_PRESCALE, prescale);
    PCA9685_Write8(PCA9685_MODE1, oldmode);

    HAL_Delay(5);

    PCA9685_Write8(PCA9685_MODE1, oldmode | 0xA0);  // restart + auto increment
}

static void PCA9685_SetPWM(uint8_t channel, uint16_t on, uint16_t off)
{
    uint8_t data[4];

    if (channel > 15)
    {
        return;
    }

    data[0] = on & 0xFF;
    data[1] = on >> 8;
    data[2] = off & 0xFF;
    data[3] = off >> 8;

    HAL_I2C_Mem_Write(&hi2c2,
                      PCA9685_ADDR,
                      PCA9685_LED0_ON_L + 4 * channel,
                      I2C_MEMADD_SIZE_8BIT,
                      data,
                      4,
                      100);
}

static void PCA9685_SetServoUs(uint8_t channel, uint16_t pulse_us)
{
    uint16_t tick;

    pulse_us = (uint16_t)CLAMP(pulse_us, SERVO_MIN_US, SERVO_MAX_US);

    /*
        50Hz周期 = 20ms = 20000us
        PCA9685一周期分成4096份
        tick = pulse_us * 4096 / 20000
    */
    tick = (uint16_t)((uint32_t)pulse_us * 4096UL / 20000UL);

    PCA9685_SetPWM(channel, 0, tick);
}

static void PCA9685_Init(void)
{
    HAL_Delay(20);

    if (!PCA9685_IsReady())
    {
        User_SendText("\r\nERROR: PCA9685 not found on I2C2. Check PB10/PB11/VCC/GND/OE.\r\n");
        g_fault_flag = 1;
        HAL_GPIO_WritePin(FAULT_LED_GPIO_Port, FAULT_LED_Pin, GPIO_PIN_SET);
        return;
    }

    PCA9685_Write8(PCA9685_MODE1, 0x00);
    PCA9685_Write8(PCA9685_MODE2, 0x04);     // 输出推挽模式

    PCA9685_SetPWMFreq(PCA9685_SERVO_FREQ);

    HAL_Delay(20);

    User_SendText("\r\nPCA9685 init OK.\r\n");
}

/* -------------------- 电机控制部分 -------------------- */

static void Motor_Enable(uint8_t en)
{
    HAL_GPIO_WritePin(MOTOR_EN_GPIO_Port, MOTOR_EN_Pin, en ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void Motor_SetPWM(uint8_t motor_id, int16_t pwm)
{
    uint16_t compare = 0;

    pwm = CLAMP(pwm, -MOTOR_PWM_MAX, MOTOR_PWM_MAX);
    compare = (uint16_t)((pwm >= 0) ? pwm : -pwm);

    switch (motor_id)
    {
        case 1:
            if (pwm > 0)
            {
                HAL_GPIO_WritePin(M1_IN1_GPIO_Port, M1_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M1_IN2_GPIO_Port, M1_IN2_Pin, GPIO_PIN_SET);
            }
            else if (pwm < 0)
            {
                HAL_GPIO_WritePin(M1_IN1_GPIO_Port, M1_IN1_Pin, GPIO_PIN_SET);
                HAL_GPIO_WritePin(M1_IN2_GPIO_Port, M1_IN2_Pin, GPIO_PIN_RESET);
            }
            else
            {
                HAL_GPIO_WritePin(M1_IN1_GPIO_Port, M1_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M1_IN2_GPIO_Port, M1_IN2_Pin, GPIO_PIN_RESET);
            }

            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_1, compare);
            g_motor[0].pwm_cmd = pwm;
            break;

        case 2:
            if (pwm > 0)
            {
                HAL_GPIO_WritePin(M2_IN1_GPIO_Port, M2_IN1_Pin, GPIO_PIN_SET);
                HAL_GPIO_WritePin(M2_IN2_GPIO_Port, M2_IN2_Pin, GPIO_PIN_RESET);
            }
            else if (pwm < 0)
            {
                HAL_GPIO_WritePin(M2_IN1_GPIO_Port, M2_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M2_IN2_GPIO_Port, M2_IN2_Pin, GPIO_PIN_SET);
            }
            else
            {
                HAL_GPIO_WritePin(M2_IN1_GPIO_Port, M2_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M2_IN2_GPIO_Port, M2_IN2_Pin, GPIO_PIN_RESET);
            }

            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, compare);
            g_motor[1].pwm_cmd = pwm;
            break;

        case 3:
            if (pwm > 0)
            {
                HAL_GPIO_WritePin(M3_IN1_GPIO_Port, M3_IN1_Pin, GPIO_PIN_SET);
                HAL_GPIO_WritePin(M3_IN2_GPIO_Port, M3_IN2_Pin, GPIO_PIN_RESET);
            }
            else if (pwm < 0)
            {
                HAL_GPIO_WritePin(M3_IN1_GPIO_Port, M3_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M3_IN2_GPIO_Port, M3_IN2_Pin, GPIO_PIN_SET);
            }
            else
            {
                HAL_GPIO_WritePin(M3_IN1_GPIO_Port, M3_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M3_IN2_GPIO_Port, M3_IN2_Pin, GPIO_PIN_RESET);
            }

            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_3, compare);
            g_motor[2].pwm_cmd = pwm;
            break;

        case 4:
            if (pwm > 0)
            {
                HAL_GPIO_WritePin(M4_IN1_GPIO_Port, M4_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M4_IN2_GPIO_Port, M4_IN2_Pin, GPIO_PIN_SET);
            }
            else if (pwm < 0)
            {
                HAL_GPIO_WritePin(M4_IN1_GPIO_Port, M4_IN1_Pin, GPIO_PIN_SET);
                HAL_GPIO_WritePin(M4_IN2_GPIO_Port, M4_IN2_Pin, GPIO_PIN_RESET);
            }
            else
            {
                HAL_GPIO_WritePin(M4_IN1_GPIO_Port, M4_IN1_Pin, GPIO_PIN_RESET);
                HAL_GPIO_WritePin(M4_IN2_GPIO_Port, M4_IN2_Pin, GPIO_PIN_RESET);
            }

            __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_4, compare);
            g_motor[3].pwm_cmd = pwm;
            break;

        default:
            break;
    }
}

static void Motor_StopAll(void)
{
    Motor_SetPWM(1, 0);
    Motor_SetPWM(2, 0);
    Motor_SetPWM(3, 0);
    Motor_SetPWM(4, 0);
}

static void Car_Forward(void)
{
    Motor_Enable(1);

    Motor_SetPWM(1,  MOTOR_MOVE_PWM);
    Motor_SetPWM(2,  MOTOR_MOVE_PWM);
    Motor_SetPWM(3,  MOTOR_MOVE_PWM);
    Motor_SetPWM(4,  MOTOR_MOVE_PWM);
}

static void Car_Backward(void)
{
    Motor_Enable(1);

    Motor_SetPWM(1, -MOTOR_MOVE_PWM);
    Motor_SetPWM(2, -MOTOR_MOVE_PWM);
    Motor_SetPWM(3, -MOTOR_MOVE_PWM);
    Motor_SetPWM(4, -MOTOR_MOVE_PWM);
}

static void Car_TurnLeft(void)
{
    Motor_Enable(1);

    /*
        左转：
        左侧 M1/M2 后退，右侧 M3/M4 前进。
        小车太重时，先用较大 PWM 冲击一小段时间，
        再降到持续转弯 PWM。
    */
    Motor_SetPWM(1, -MOTOR_TURN_START_PWM);
    Motor_SetPWM(2, -MOTOR_TURN_START_PWM);
    Motor_SetPWM(3,  MOTOR_TURN_START_PWM);
    Motor_SetPWM(4,  MOTOR_TURN_START_PWM);

    HAL_Delay(MOTOR_TURN_START_TIME_MS);

    Motor_SetPWM(1, -MOTOR_TURN_PWM);
    Motor_SetPWM(2, -MOTOR_TURN_PWM);
    Motor_SetPWM(3,  MOTOR_TURN_PWM);
    Motor_SetPWM(4,  MOTOR_TURN_PWM);
}

static void Car_TurnRight(void)
{
    Motor_Enable(1);

    /*
        右转：
        左侧 M1/M2 前进，右侧 M3/M4 后退。
        小车太重时，先用较大 PWM 冲击一小段时间，
        再降到持续转弯 PWM。
    */
    Motor_SetPWM(1,  MOTOR_TURN_START_PWM);
    Motor_SetPWM(2,  MOTOR_TURN_START_PWM);
    Motor_SetPWM(3, -MOTOR_TURN_START_PWM);
    Motor_SetPWM(4, -MOTOR_TURN_START_PWM);

    HAL_Delay(MOTOR_TURN_START_TIME_MS);

    Motor_SetPWM(1,  MOTOR_TURN_PWM);
    Motor_SetPWM(2,  MOTOR_TURN_PWM);
    Motor_SetPWM(3, -MOTOR_TURN_PWM);
    Motor_SetPWM(4, -MOTOR_TURN_PWM);
}

/* -------------------- 舵机控制部分：PCA9685 -------------------- */

static uint16_t Servo_AngleToUs(uint8_t angle)
{
    if (angle > 180)
    {
        angle = 180;
    }

    return SERVO_MIN_US + (uint16_t)((uint32_t)angle * (SERVO_MAX_US - SERVO_MIN_US) / 180);
}

static void Servo_SetUs(uint8_t servo_id, uint16_t pulse_us)
{
    pulse_us = (uint16_t)CLAMP(pulse_us, SERVO_MIN_US, SERVO_MAX_US);

    switch (servo_id)
    {
        case SERVO_BOTTOM_ID:
            PCA9685_SetServoUs(PCA9685_CH_BOTTOM, pulse_us);
            g_servo_us[0] = pulse_us;
            break;

        case SERVO_MIDDLE_ID:
            PCA9685_SetServoUs(PCA9685_CH_MIDDLE, pulse_us);
            g_servo_us[1] = pulse_us;
            break;

        case SERVO_TOP_ID:
            PCA9685_SetServoUs(PCA9685_CH_TOP, pulse_us);
            g_servo_us[2] = pulse_us;
            break;

        default:
            break;
    }
}

static void Servo_SetAngle(uint8_t servo_id, uint8_t angle)
{
    Servo_SetUs(servo_id, Servo_AngleToUs(angle));
}

static void Servo_InitPose(void)
{
    Servo_SetAngle(SERVO_BOTTOM_ID, 120);
    HAL_Delay(200);

    Servo_SetAngle(SERVO_MIDDLE_ID, 120);
    HAL_Delay(200);

    Servo_SetAngle(SERVO_TOP_ID, 180);
    HAL_Delay(200);

    User_SendText("\r\nServo init pose: bottom=120, middle=90, top=180\r\n");
}

static void Servo_Reset(void)
{
    Servo_InitPose();
    User_SendText("\r\nCMD Z OK: servo reset\r\n");
}

/*
    串口发送 L：
    最底下舵机 -> 90°
    中间舵机   -> 60°
    最上面舵机 -> 90°
*/
static void Servo_ActionLeft(void)
{
    Servo_SetAngle(SERVO_BOTTOM_ID, 180);
    HAL_Delay(300);

    Servo_SetAngle(SERVO_MIDDLE_ID, 60);
    HAL_Delay(300);

    Servo_SetAngle(SERVO_TOP_ID, 180);

    User_SendText("\r\nCMD L OK: bottom=90, middle=120, top=90\r\n");
}

/*
    串口发送 R：
    最底下舵机 -> 50°
    中间舵机   -> 110°
    最上面舵机 -> 170°
*/
static void Servo_ActionRight(void)
{
    Servo_SetAngle(SERVO_BOTTOM_ID, 0);
    HAL_Delay(300);

    Servo_SetAngle(SERVO_MIDDLE_ID, 60);
    HAL_Delay(300);

    Servo_SetAngle(SERVO_TOP_ID, 180);

    User_SendText("\r\nCMD R OK: bottom=50, middle=110, top=170\r\n");
}


/* -------------------- 新增：摄像头二自由度云台控制：TIM12 -------------------- */

static uint16_t Gimbal_AngleToUs(uint8_t angle)
{
    if (angle > 180)
    {
        angle = 180;
    }

    return GIMBAL_MIN_US + (uint16_t)((uint32_t)angle * (GIMBAL_MAX_US - GIMBAL_MIN_US) / 180);
}

static void Gimbal_SetYawUs(uint16_t pulse_us)
{
    pulse_us = (uint16_t)CLAMP(pulse_us, GIMBAL_MIN_US, GIMBAL_MAX_US);
    __HAL_TIM_SET_COMPARE(&htim12, TIM_CHANNEL_1, pulse_us);
    g_gimbal_yaw_us = pulse_us;
}

static void Gimbal_SetPitchUs(uint16_t pulse_us)
{
    pulse_us = (uint16_t)CLAMP(pulse_us, GIMBAL_MIN_US, GIMBAL_MAX_US);
    __HAL_TIM_SET_COMPARE(&htim12, TIM_CHANNEL_2, pulse_us);
    g_gimbal_pitch_us = pulse_us;
}

static void Gimbal_SetYawAngle(uint8_t angle)
{
    Gimbal_SetYawUs(Gimbal_AngleToUs(angle));
}

static void Gimbal_SetPitchAngle(uint8_t angle)
{
    Gimbal_SetPitchUs(Gimbal_AngleToUs(angle));
}

static void Gimbal_InitPose(void)
{
    Gimbal_SetYawAngle(GIMBAL_YAW_CENTER_ANGLE);
    HAL_Delay(200);

    Gimbal_SetPitchAngle(GIMBAL_PITCH_DEFAULT_ANGLE);
    HAL_Delay(200);

    User_SendText("\r\nGimbal init pose: yaw=center, pitch=default\r\n");
}

/*
    新增串口命令：
    a/A : 摄像头云台看左边
    d/D : 摄像头云台看右边
    c/C : 摄像头云台回中
    w/W : 摄像头抬头
    s/S : 摄像头低头
    v/V : 摄像头默认俯仰
*/
static void Gimbal_LookLeft(void)
{
    Gimbal_SetYawAngle(GIMBAL_YAW_LEFT_ANGLE);
    User_SendText("\r\nCMD a OK: gimbal yaw left\r\n");
}

static void Gimbal_LookRight(void)
{
    Gimbal_SetYawAngle(GIMBAL_YAW_RIGHT_ANGLE);
    User_SendText("\r\nCMD d OK: gimbal yaw right\r\n");
}

static void Gimbal_LookCenter(void)
{
    Gimbal_SetYawAngle(GIMBAL_YAW_CENTER_ANGLE);
    User_SendText("\r\nCMD c OK: gimbal yaw center\r\n");
}

static void Gimbal_PitchUp(void)
{
    Gimbal_SetPitchAngle(GIMBAL_PITCH_UP_ANGLE);
    User_SendText("\r\nCMD w OK: gimbal pitch up\r\n");
}

static void Gimbal_PitchDown(void)
{
    Gimbal_SetPitchAngle(GIMBAL_PITCH_DOWN_ANGLE);
    User_SendText("\r\nCMD s OK: gimbal pitch down\r\n");
}

static void Gimbal_PitchDefault(void)
{
    Gimbal_SetPitchAngle(GIMBAL_PITCH_DEFAULT_ANGLE);
    User_SendText("\r\nCMD v OK: gimbal pitch default\r\n");
}

/* -------------------- 两个水泵控制 -------------------- */

/*
    两个水泵 GPIO 二次初始化：
    作用：即使 CubeMX 忘记把 PC4/PC5 配成输出，这里也能保证可用。

    当前定义：
        PUMP1 -> PC4
        PUMP2 -> PC5

    继电器推荐接法：
        STM32 GPIO -> 继电器 IN
        继电器 VCC -> 5V
        继电器 GND -> STM32 GND
        水泵电源正极 -> COM
        NO -> 水泵正极
        水泵负极 -> 电源负极

    NC 不接。使用 NO 可以保证上电默认不喷水。
*/
static void Pump_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOC_CLK_ENABLE();

    /* 先输出“关闭”电平，防止初始化瞬间水泵误动作 */
#if PUMP1_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_RESET);
#endif

#if PUMP2_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_RESET);
#endif

    GPIO_InitStruct.Pin = PUMP1_Pin | PUMP2_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    g_pump1_on = 0;
    g_pump2_on = 0;
}

static void Pump1_On(void)
{
#if PUMP1_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_RESET);
#else
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_SET);
#endif

    g_pump1_on = 1;
}

static void Pump1_Off(void)
{
#if PUMP1_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP1_GPIO_Port, PUMP1_Pin, GPIO_PIN_RESET);
#endif

    g_pump1_on = 0;
}

static void Pump2_On(void)
{
#if PUMP2_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_RESET);
#else
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_SET);
#endif

    g_pump2_on = 1;
}

static void Pump2_Off(void)
{
#if PUMP2_ACTIVE_LOW
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_SET);
#else
    HAL_GPIO_WritePin(PUMP2_GPIO_Port, PUMP2_Pin, GPIO_PIN_RESET);
#endif

    g_pump2_on = 0;
}

/* -------------------- 编码器 -------------------- */

static int16_t Encoder_ReadRaw16(TIM_HandleTypeDef *htim)
{
    return (int16_t)__HAL_TIM_GET_COUNTER(htim);
}

static int16_t Encoder_ReadDelta(TIM_HandleTypeDef *htim, int16_t *last_raw)
{
    int16_t now = Encoder_ReadRaw16(htim);
    int16_t delta = (int16_t)(now - *last_raw);
    *last_raw = now;
    return delta;
}

static void Encoder_Update10ms(void)
{
    g_motor[0].enc_delta_10ms = Encoder_ReadDelta(&htim2, &enc_last_raw[0]);
    g_motor[1].enc_delta_10ms = Encoder_ReadDelta(&htim3, &enc_last_raw[1]);
    g_motor[2].enc_delta_10ms = Encoder_ReadDelta(&htim4, &enc_last_raw[2]);
    g_motor[3].enc_delta_10ms = Encoder_ReadDelta(&htim8, &enc_last_raw[3]);

    g_motor[0].enc_total += g_motor[0].enc_delta_10ms;
    g_motor[1].enc_total += g_motor[1].enc_delta_10ms;
    g_motor[2].enc_total += g_motor[2].enc_delta_10ms;
    g_motor[3].enc_total += g_motor[3].enc_delta_10ms;
}

/* -------------------- 安全保护 -------------------- */

static void Safety_Check(void)
{
    if (HAL_GPIO_ReadPin(ESTOP_GPIO_Port, ESTOP_Pin) == GPIO_PIN_RESET)
    {
        g_estop_latched = 1;
    }

    if (g_estop_latched)
    {
        Motor_StopAll();
        Pump1_Off();
        Pump2_Off();
        Motor_Enable(0);

        g_fault_flag = 1;
        HAL_GPIO_WritePin(FAULT_LED_GPIO_Port, FAULT_LED_Pin, GPIO_PIN_SET);
    }

}

/* -------------------- 串口帮助与状态打印 -------------------- */

static void User_SendHelp(void)
{
    User_SendText(
        "\r\n=== STM32F407 Smart Agriculture Robot Cmd ===\r\n"
        "h : help\r\n"
        "g : send status\r\n"
        "0 : stop all motor\r\n"
        "1 : forward\r\n"
        "2 : backward\r\n"
        "7 : turn left\r\n"
        "8 : turn right\r\n"
        "\r\n"
        "L : spray/working servo action left\r\n"
        "R : spray/working servo action right\r\n"
        "Z : spray/working servo reset to init pose\r\n"
        "\r\n"
        "a/A : camera gimbal look left  (PB14 TIM12_CH1)\r\n"
        "d/D : camera gimbal look right (PB14 TIM12_CH1)\r\n"
        "c/C : camera gimbal center     (PB14 TIM12_CH1)\r\n"
        "w/W : camera gimbal pitch up   (PB15 TIM12_CH2)\r\n"
        "s/S : camera gimbal pitch down (PB15 TIM12_CH2)\r\n"
        "v/V : camera gimbal pitch default\r\n"
        "\r\n"
        "p : pump1 toggle\r\n"
        "q : pump2 toggle\r\n"
        "P : pump1 off\r\n"
        "Q : pump2 off\r\n"
        "x : both pumps off\r\n"
        "k : emergency stop latch\r\n"
        "u/U : clear estop latch\r\n"
        "m : motor enable\r\n"
        "n : motor disable\r\n"
        "=============================================\r\n");
}

static void User_SendStatus(void)
{
    snprintf(uart_tx_buf, sizeof(uart_tx_buf),
             "\r\nESTOP=%u FAULT=%u PUMP1=%u PUMP2=%u\r\n"
             "M1 pwm=%d d10=%d total=%ld\r\n"
             "M2 pwm=%d d10=%d total=%ld\r\n"
             "M3 pwm=%d d10=%d total=%ld\r\n"
             "M4 pwm=%d d10=%d total=%ld\r\n"
             "SERVO_BOTTOM_US=%u SERVO_MIDDLE_US=%u SERVO_TOP_US=%u\r\n"
             "GIMBAL_YAW_US=%u GIMBAL_PITCH_US=%u\r\n",
             g_estop_latched,
             g_fault_flag,
             g_pump1_on,
             g_pump2_on,
             g_motor[0].pwm_cmd, g_motor[0].enc_delta_10ms, (long)g_motor[0].enc_total,
             g_motor[1].pwm_cmd, g_motor[1].enc_delta_10ms, (long)g_motor[1].enc_total,
             g_motor[2].pwm_cmd, g_motor[2].enc_delta_10ms, (long)g_motor[2].enc_total,
             g_motor[3].pwm_cmd, g_motor[3].enc_delta_10ms, (long)g_motor[3].enc_total,
             g_servo_us[0], g_servo_us[1], g_servo_us[2],
             g_gimbal_yaw_us, g_gimbal_pitch_us);

    User_SendText(uart_tx_buf);
}

/* -------------------- 串口命令处理 -------------------- */

static void User_HandleUartByte(uint8_t ch)
{
    switch (ch)
    {
        case 'h':
            User_SendHelp();
            break;

        case 'g':
            User_SendStatus();
            break;

        case '0':
            Motor_StopAll();
            break;

        case '1':
            if (!g_estop_latched) Car_Forward();
            break;

        case '2':
            if (!g_estop_latched) Car_Backward();
            break;

        case '7':
            if (!g_estop_latched) Car_TurnLeft();
            break;

        case '8':
            if (!g_estop_latched) Car_TurnRight();
            break;

        case 'L':
        case 'l':
            Servo_ActionLeft();
            break;

        case 'R':
        case 'r':
            Servo_ActionRight();
            break;

        case 'Z':
        case 'z':
            Servo_Reset();
            break;

        /*
            新增摄像头云台命令：
            a/d/c 控制左右看，w/s/v 控制俯仰。
            注意：小车停止仍然是 '0'，所以这里 's' 用作摄像头低头。
        */
        case 'a':
        case 'A':
            Gimbal_LookLeft();
            break;

        case 'd':
        case 'D':
            Gimbal_LookRight();
            break;

        case 'c':
        case 'C':
            Gimbal_LookCenter();
            break;

        case 'w':
        case 'W':
            Gimbal_PitchUp();
            break;

        case 's':
        case 'S':
            Gimbal_PitchDown();
            break;

        case 'v':
        case 'V':
            Gimbal_PitchDefault();
            break;

        case 'p':
            if (g_pump1_on) Pump1_Off();
            else Pump1_On();
            break;

        case 'q':
            if (g_pump2_on) Pump2_Off();
            else Pump2_On();
            break;

        case 'P':
            Pump1_Off();
            User_SendText("\r\nPUMP1 OFF\r\n");
            break;

        case 'Q':
            Pump2_Off();
            User_SendText("\r\nPUMP2 OFF\r\n");
            break;

        case 'x':
            Pump1_Off();
            Pump2_Off();
            User_SendText("\r\nPUMP1 OFF, PUMP2 OFF\r\n");
            break;

        case 'k':
            g_estop_latched = 1;
            Safety_Check();
            User_SendText("\r\nESTOP LATCHED\r\n");
            break;

        case 'u':
        case 'U':
            if (HAL_GPIO_ReadPin(ESTOP_GPIO_Port, ESTOP_Pin) == GPIO_PIN_SET)
            {
                g_estop_latched = 0;
                g_fault_flag = 0;

                HAL_GPIO_WritePin(FAULT_LED_GPIO_Port, FAULT_LED_Pin, GPIO_PIN_RESET);

                Motor_Enable(1);
                User_SendText("\r\nESTOP CLEARED\r\n");
            }
            else
            {
                User_SendText("\r\nESTOP PIN STILL LOW\r\n");
            }
            break;

        case 'm':
            Motor_Enable(1);
            User_SendText("\r\nMOTOR ENABLE\r\n");
            break;

        case 'n':
            Motor_Enable(0);
            Motor_StopAll();
            User_SendText("\r\nMOTOR DISABLE\r\n");
            break;

        case '\r':
        case '\n':
            break;

        default:
            break;
    }
}

/* -------------------- APP 初始化与主循环 -------------------- */

static void App_Init(void)
{
    memset(g_motor, 0, sizeof(g_motor));

    HAL_GPIO_WritePin(RUN_LED_GPIO_Port, RUN_LED_Pin, GPIO_PIN_SET);
    User_Beep(60);


    User_SendHelp();
    User_SendStatus();
}

static void App_Loop(void)
{
    static uint32_t t10  = 0;
    static uint32_t t100 = 0;
    static uint32_t t500 = 0;

    uint32_t now = HAL_GetTick();

    /*
        串口命令在主循环里处理。
        不要在 HAL_UART_RxCpltCallback 中直接执行舵机动作，
        因为舵机动作里有 HAL_Delay。
    */
    if (g_uart_cmd_pending != 0)
    {
        uint8_t cmd = g_uart_cmd_pending;
        g_uart_cmd_pending = 0;

        User_HandleUartByte(cmd);
    }

    if ((now - t10) >= 10)
    {
        t10 = now;
        Encoder_Update10ms();
    }


    if ((now - t100) >= 100)
    {
        t100 = now;
        Safety_Check();
        HAL_GPIO_TogglePin(COMM_LED_GPIO_Port, COMM_LED_Pin);
    }

    if ((now - t500) >= 500)
    {
        t500 = now;
        HAL_GPIO_TogglePin(RUN_LED_GPIO_Port, RUN_LED_Pin);

#if DEBUG_PRINT_ENABLE
        User_SendStatus();
#endif
    }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_ADC1_Init();
  MX_TIM1_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();
  MX_TIM4_Init();
  MX_TIM8_Init();
  MX_TIM9_Init();
  MX_TIM10_Init();
  MX_TIM11_Init();
  MX_USART2_UART_Init();
  MX_I2C2_Init();
  MX_TIM12_Init();
  /* USER CODE BEGIN 2 */

  /*
      上电安全顺序：
      1. 先把两个水泵 GPIO 初始化为关闭状态
      2. 再执行整车安全状态初始化
      3. 再启动 PWM、编码器、PCA9685、串口接收等外设
  */
  Pump_GPIO_Init();
  User_SetSafeState();
  User_StartPeripherals();
  App_Init();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    App_Loop();
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        g_uart_cmd_pending = uart2_rx_byte;
        HAL_UART_Receive_IT(&huart2, &uart2_rx_byte, 1);
    }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
