// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2022 wind
// SPDX-FileContributor: wind (573966@qq.com)

package main

import (
	"context"
	"flag"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	rv8 "github.com/redis/go-redis/v9"
	"github.com/wind-c/comqtt/v2/cluster/log"
	"github.com/wind-c/comqtt/v2/config"
	"github.com/wind-c/comqtt/v2/mqtt"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/auth"
	"github.com/wind-c/comqtt/v2/mqtt/hooks/storage/redis"
	"github.com/wind-c/comqtt/v2/mqtt/listeners"
	"github.com/wind-c/comqtt/v2/mqtt/rest"
	lauth "github.com/wind-c/comqtt/v2/plugin/auth"
	pauth "github.com/wind-c/comqtt/v2/plugin/auth/postgresql"
)

func pprof() {
	go func() {
		log.Info("listen pprof", "error", http.ListenAndServe(":6060", nil))
	}()
}

func main() {
	sigCtx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	err := realMain(sigCtx)
	onError(err, "")
}

func realMain(ctx context.Context) error {
	var err error
	var confFile string
	cfg := config.New()

	flag.StringVar(&confFile, "conf", "", "read the program parameters from the config file")
	flag.StringVar(&cfg.Mqtt.TCP, "tcp", ":1883", "network address for Mqtt TCP listener")
	flag.StringVar(&cfg.Mqtt.WS, "ws", ":1882", "network address for Mqtt Websocket listener")
	flag.StringVar(&cfg.Mqtt.HTTP, "http", ":8080", "network address for web info dashboard listener")
	flag.BoolVar(&cfg.Log.Enable, "log-enable", true, "log enabled or not")
	//flag.StringVar(&cfg.Log.Filename, "log-file", "./logs/comqtt.log", "log filename")
	//parse arguments
	flag.Parse()

	// Force stdout logging for docker
	cfg.Log.Output = log.OutputConsole

	//load config file
	if len(confFile) > 0 {
		if cfg, err = config.Load(confFile); err != nil {
			onError(err, "")
		}
	}

	//enable pprof
	if cfg.PprofEnable {
		pprof()
	}

	//init log
	log.Init(&cfg.Log)

	// create server instance and init hooks
	cfg.Mqtt.Options.Logger = log.Default()
	server := mqtt.New(&cfg.Mqtt.Options)
	log.Info("comqtt server initializing...")

	// Initialize custom storage and auth
	initStorage(server)
	initAuth(server)

	// gen tls config
	var listenerConfig *listeners.Config
	if tlsConfig, err := config.GenTlsConfig(cfg); err != nil {
		onError(err, "")
	} else {
		if tlsConfig != nil {
			listenerConfig = &listeners.Config{TLSConfig: tlsConfig}
		}
	}

	// add tcp listener
	tcp := listeners.NewTCP("tcp", cfg.Mqtt.TCP, listenerConfig)
	onError(server.AddListener(tcp), "add tcp listener")

	// add websocket listener
	ws := listeners.NewWebsocket("ws", cfg.Mqtt.WS, listenerConfig)
	onError(server.AddListener(ws), "add websocket listener")

	// add http listener
	http := listeners.NewHTTP("stats", cfg.Mqtt.HTTP, nil, rest.New(server).GenHandlers())
	onError(server.AddListener(http), "add http listener")

	errCh := make(chan error, 1)
	// start server
	go func() {
		err := server.Serve()
		if err != nil {
			errCh <- err
		}
	}()

	select {
	case err := <-errCh:
		onError(err, "server error")
	case <-ctx.Done():
		log.Warn("caught signal, stopping...")
	}
	server.Close()
	log.Info("main.go finished")
	return nil
}

func initAuth(server *mqtt.Server) {
	logMsg := "init custom auth"

	// Postgres Config
	// We assume localhost because we are in the same container/pod
	opts := pauth.Options{
		AuthMode: byte(auth.AuthUsername),
		AclMode:  byte(auth.AuthUsername),
		Dsn: pauth.DsnInfo{
			Host:          "localhost",
			Port:          5432,
			Schema:        "mqtt_db",
			SslMode:       "disable",
			LoginName:     "mqtt_user",
			LoginPassword: "mqtt_password",
			MaxOpenConns:  5,
			MaxIdleConns:  5,
		},
		Auth: pauth.AuthTable{
			Table:          "core_mqttuser",
			UserColumn:     "username",
			PasswordColumn: "password",
			// Cast boolean to int for comqtt expectation (1=allow)
			AllowColumn:  "case when is_superuser then 1 else 0 end",
			PasswordHash: lauth.HashBcrypt,
		},

		Acl: pauth.AclTable{
			// Join to get username from user_id
			Table:        "core_mqttacl T1 INNER JOIN core_mqttuser T2 ON T1.user_id = T2.id",
			UserColumn:   "T2.username",
			TopicColumn:  "T1.topic",
			AccessColumn: "T1.access",
		},
	}

	onError(server.AddHook(new(pauth.Auth), &opts), logMsg)
}

func initStorage(server *mqtt.Server) {
	logMsg := "init custom storage (redis)"

	opts := redis.Options{
		HPrefix: "comqtt:",
		Options: &rv8.Options{
			Addr:     "localhost:6379",
			DB:       0,
			Password: "", // No password by default in our container setup
		},
	}
	onError(server.AddHook(new(redis.Hook), &opts), logMsg)
}

// onError handle errors and simplify code
func onError(err error, msg string) {
	if err != nil {
		log.Error(msg, "error", err)
		os.Exit(1)
	}
}
