// ============================================================
// Piezo Microphone - ESP32 Firmware
// ============================================================
// דוגם אות מפיזו דרך ADC1 (GPIO34) באמצעות I2S DMA
// עושה oversampling ב-64kHz ו-decimation ל-16kHz
// שולח את הנתונים דרך USB Serial למחשב
// ============================================================

#include <driver/i2s.h>
#include <driver/adc.h>
#include <WiFi.h>
#include <esp_bt.h>
#include <soc/syscon_reg.h>

// --- הגדרות דגימה ---
// אנחנו דוגמים ב-64kHz אבל I2S דוגם שני ערוצים,
// אז צריך להגדיר 128kHz כדי לקבל 64kHz אפקטיבי
#define I2S_SAMPLE_RATE     128000  // 128kHz → 64kHz אפקטיבי (כפול בגלל stereo)
#define OVERSAMPLE_RATIO    4       // 64kHz / 4 = 16kHz אפקטיבי אחרי decimation
#define EFFECTIVE_RATE      16000   // קצב הדגימה הסופי שנשלח למחשב

// --- הגדרות I2S DMA ---
#define I2S_DMA_BUF_COUNT   4       // מספר באפרים ב-DMA
#define I2S_DMA_BUF_LEN     1024    // דגימות לכל באפר

// --- הגדרות Serial ---
#define SERIAL_BAUD         921600  // מהירות גבוהה לשליחת אודיו

// --- פין ADC ---
// GPIO34 = ADC1_CHANNEL_6
#define ADC_PIN             ADC1_CHANNEL_6

// --- באפר קריאה ---
// I2S מחזיר 16-bit לכל דגימה, נקרא בלוקים
#define READ_BUF_SIZE       1024
uint16_t i2s_read_buf[READ_BUF_SIZE];

// --- משתני decimation ---
int32_t decimation_accumulator = 0;  // צובר דגימות ל-averaging
uint8_t decimation_count = 0;        // סופר כמה דגימות נצברו

// --- באפר שליחה ---
// באפר של דגימות אחרי decimation, מוכנות לשליחה
#define SEND_BUF_SIZE       512
uint16_t send_buf[SEND_BUF_SIZE];
uint16_t send_buf_index = 0;

// --- סנכרון ---
// header byte ששולחים לפני כל בלוק נתונים
// כדי שה-Python יוכל לזהות תחילת בלוק
#define SYNC_BYTE_1         0xAA
#define SYNC_BYTE_2         0x55

void setup() {
  // --- אתחול Serial ---
  Serial.begin(SERIAL_BAUD);
  while (!Serial) { delay(10); }
  
  // --- כיבוי WiFi ו-BT להפחתת רעש ---
  // WiFi ו-BT יוצרים רעש חשמלי שמפריע ל-ADC
  WiFi.mode(WIFI_OFF);
  esp_bt_controller_disable();
  
  // --- הגדרת ADC ---
  // 6dB attenuation: טווח מדידה מומלץ 150-1750mV
  // האות שלנו יושב על ~1.5V ± 200mV → בול בטווח
  adc1_config_width(ADC_WIDTH_BIT_12);
  adc1_config_channel_atten(ADC_PIN, ADC_ATTEN_DB_6);
  
  // --- הגדרת I2S למוד ADC ---
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_ADC_BUILT_IN),
    .sample_rate = I2S_SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S_MSB,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = I2S_DMA_BUF_COUNT,
    .dma_buf_len = I2S_DMA_BUF_LEN,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };
  
  // התקנת דרייבר I2S
  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  
  // חיבור I2S ל-ADC
  i2s_set_adc_mode(ADC_UNIT_1, ADC_PIN);
  
  // תיקון: ה-ADC של ESP32 מחזיר ערכים הפוכים כברירת מחדל
  // צריך להפוך אותם חזרה
  SET_PERI_REG_MASK(SYSCON_SARADC_CTRL2_REG, SYSCON_SARADC_SAR1_INV);
  
  // המתנה ליציבות ה-ADC
  delay(1000);
  
  // הפעלת ה-ADC דרך I2S
  i2s_adc_enable(I2S_NUM_0);
  
  // המתנה נוספת - נחוצה ליציבות
  delay(500);
  
  // ניקוי באפרים ראשוניים (מכילים זבל)
  size_t bytes_read;
  for (int i = 0; i < I2S_DMA_BUF_COUNT; i++) {
    i2s_read(I2S_NUM_0, i2s_read_buf, READ_BUF_SIZE * sizeof(uint16_t), &bytes_read, portMAX_DELAY);
  }
}

void loop() {
  size_t bytes_read = 0;
  
  // --- קריאת בלוק מ-I2S DMA ---
  // הפונקציה חוסמת עד שיש נתונים זמינים
  i2s_read(I2S_NUM_0, i2s_read_buf, READ_BUF_SIZE * sizeof(uint16_t), &bytes_read, portMAX_DELAY);
  
  int samples_read = bytes_read / sizeof(uint16_t);
  
  // --- עיבוד כל דגימה ---
  for (int i = 0; i < samples_read; i++) {
    // חילוץ 12 הביטים התחתונים (ה-ADC הוא 12-bit)
    // I2S מחזיר 16-bit, 4 ביטים עליונים הם ערוץ
    uint16_t raw_sample = i2s_read_buf[i] & 0x0FFF;
    
    // --- Decimation: צובר 4 דגימות ומחשב ממוצע ---
    decimation_accumulator += raw_sample;
    decimation_count++;
    
    if (decimation_count >= OVERSAMPLE_RATIO) {
      // ממוצע → דגימה אחת ב-16kHz
      uint16_t decimated_sample = decimation_accumulator / OVERSAMPLE_RATIO;
      
      // שמירה בבאפר השליחה
      send_buf[send_buf_index++] = decimated_sample;
      
      // איפוס ה-accumulator
      decimation_accumulator = 0;
      decimation_count = 0;
      
      // --- שליחה כשהבאפר מלא ---
      if (send_buf_index >= SEND_BUF_SIZE) {
        // שליחת sync header
        Serial.write(SYNC_BYTE_1);
        Serial.write(SYNC_BYTE_2);
        
        // שליחת גודל הבלוק (2 bytes, little-endian)
        uint16_t block_size = SEND_BUF_SIZE;
        Serial.write((uint8_t)(block_size & 0xFF));
        Serial.write((uint8_t)(block_size >> 8));
        
        // שליחת הנתונים כ-bytes (2 bytes לכל דגימה, little-endian)
        Serial.write((uint8_t*)send_buf, SEND_BUF_SIZE * sizeof(uint16_t));
        
        send_buf_index = 0;
      }
    }
  }
}
