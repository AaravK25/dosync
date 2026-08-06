#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#define SERVOMIN  125  
#define SERVOMAX  512
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
void setup() {
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(50);
  Serial.begin(9600);
  mva(0);
  ssa(0,90);
}
void ssa(int channel, int angle) {
  int pulse = map(angle, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(channel, 0, pulse);

}
void mva(int cangle){
  ssa(0,cangle);ssa(1,cangle);ssa(2,cangle);ssa(3,cangle);
}

void loop() {
  if (Serial.available() > 0) {   
    char inc = Serial.read();
    if (inc == 'b') {
      ssa(0,90);
      delay(2000);
      ssa(1, 80);
      ssa(2, 0);
      ssa(3, 0);
      delay(2000);
      ssa(1,0);
    } else if (inc == 'c') {
      ssa(0,0);
      ssa(0,10);
      ssa(0,0);
      delay(2000);
      ssa(2, 80);
      ssa(1, 0);
      ssa(3, 0);
      delay(2000);
      ssa(2,0);
    } else if (inc == 'd') {
      ssa(0,180);
      ssa(0,170);
      ssa(0,180);
      delay(2000);
      ssa(3, 100);
      ssa(2, 0);
      ssa(1, 0);
      delay(2000);
      ssa(3,0);

    }
  }
}
